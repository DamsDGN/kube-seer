import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import structlog
from sklearn.ensemble import IsolationForest
from sklearn.feature_extraction.text import TfidfVectorizer

from src.analyzer.base import BaseAnalyzer
from src.analyzer.logs import ERROR_PATTERNS
from src.config import Config
from src.models import Anomaly, Severity
from src.storage.base import BaseStorage

logger = structlog.get_logger()

MAX_BUFFER_SIZE = 500
MIN_BUFFER_FOR_MODEL = 50
MAX_OUTLIERS_PER_CYCLE = 5
OUTLIER_SCORE_THRESHOLD = -0.1
SPIKE_MIN_COUNT = 5
SPIKE_MIN_SUDDEN = 10
SPIKE_RATIO_CRITICAL = 10.0
SPIKE_RATIO_WARNING = 3.0

_ERROR_LOG_SHOULD = [
    {"match": {"log": "ERROR"}},
    {"match": {"log": "FATAL"}},
    {"match": {"log": "CRITICAL"}},
    {"match": {"log": "WARN"}},
    {"match": {"log": "Exception"}},
]


class LogInsightAnalyzer(BaseAnalyzer):
    def __init__(self, config: Config, storage: BaseStorage):
        self._config = config
        self._storage = storage
        self._message_buffer: List[str] = []
        self._vectorizer: Optional[TfidfVectorizer] = None
        self._model: Optional[IsolationForest] = None

    async def analyze(self) -> List[Anomaly]:  # type: ignore[override]
        anomalies: List[Anomaly] = []
        anomalies.extend(await self._detect_spikes())
        anomalies.extend(await self._detect_outliers())
        return anomalies

    async def update_model(self, **kwargs) -> None:
        logs = await self._fetch_error_logs()
        messages = [log.get("log", "") for log in logs if log.get("log")]
        self._message_buffer.extend(messages)
        if len(self._message_buffer) > MAX_BUFFER_SIZE:
            self._message_buffer = self._message_buffer[-MAX_BUFFER_SIZE:]
        if len(self._message_buffer) >= MIN_BUFFER_FOR_MODEL:
            self._fit_model()

    # ── private ───────────────────────────────────────────────────────────────

    def _fit_model(self) -> None:
        try:
            self._vectorizer = TfidfVectorizer(max_features=500, ngram_range=(1, 2))
            tfidf = self._vectorizer.fit_transform(self._message_buffer)
            self._model = IsolationForest(
                contamination=self._config.ml_anomaly_threshold,
                n_estimators=100,
                random_state=42,
            )
            self._model.fit(tfidf.toarray())
            logger.info(
                "log_insight_analyzer.model_trained",
                samples=len(self._message_buffer),
            )
        except Exception as e:
            logger.error("log_insight_analyzer.model_train_error", error=str(e))

    async def _detect_spikes(self) -> List[Anomaly]:
        aggs = {
            "by_app": {
                "terms": {
                    "field": "kubernetes.labels.app.keyword",
                    "size": 20,
                    "missing": "__unknown__",
                }
            }
        }
        query_n = {
            "bool": {
                "must": [{"range": {"@timestamp": {"gte": "now-5m"}}}],
                "should": _ERROR_LOG_SHOULD,
                "minimum_should_match": 1,
            }
        }
        query_n1 = {
            "bool": {
                "must": [{"range": {"@timestamp": {"gte": "now-10m", "lt": "now-5m"}}}],
                "should": _ERROR_LOG_SHOULD,
                "minimum_should_match": 1,
            }
        }
        try:
            aggs_n = await self._storage.aggregate(
                index=self._config.elasticsearch_indices_logs,
                query_body=query_n,
                aggs=aggs,
            )
            aggs_n1 = await self._storage.aggregate(
                index=self._config.elasticsearch_indices_logs,
                query_body=query_n1,
                aggs=aggs,
            )
        except Exception as e:
            logger.error("log_insight_analyzer.spike_query_error", error=str(e))
            return []

        counts_n: Dict[str, int] = {
            b["key"]: b["doc_count"]
            for b in aggs_n.get("by_app", {}).get("buckets", [])
        }
        counts_n1: Dict[str, int] = {
            b["key"]: b["doc_count"]
            for b in aggs_n1.get("by_app", {}).get("buckets", [])
        }

        anomalies = []
        for app, count_n in counts_n.items():
            if app == "__unknown__":
                continue
            count_n1 = counts_n1.get(app, 0)
            anomaly = self._evaluate_spike(app, count_n, count_n1)
            if anomaly:
                anomalies.append(anomaly)
        return anomalies

    def _evaluate_spike(
        self, app: str, count_n: int, count_n1: int
    ) -> Optional[Anomaly]:
        if count_n1 == 0 and count_n >= SPIKE_MIN_SUDDEN:
            severity = Severity.CRITICAL
            ratio_val: float = count_n  # count_n / 1
            ratio_str = f"{ratio_val:.1f}"
        elif count_n < SPIKE_MIN_COUNT:
            return None
        else:
            ratio_val = count_n / (count_n1 + 1)
            if ratio_val >= SPIKE_RATIO_CRITICAL:
                severity = Severity.CRITICAL
            elif ratio_val >= SPIKE_RATIO_WARNING:
                severity = Severity.WARNING
            else:
                return None
            ratio_str = f"{ratio_val:.1f}"

        pct = ((count_n - count_n1) / (count_n1 + 1)) * 100
        description = (
            f"Error spike on deployment {app}: "
            f"{count_n1} \u2192 {count_n} errors (+{pct:.0f}% in 5min)"
        )
        return Anomaly(
            anomaly_id=str(uuid.uuid4()),
            source="logs_ml",
            severity=severity,
            resource_type="deployment",
            resource_name=app,
            namespace="",
            description=description,
            score=1.0 if severity == Severity.CRITICAL else 0.7,
            details={
                "previous": count_n1,
                "current": count_n,
                "ratio": ratio_str,
                "window_minutes": 5,
            },
            timestamp=datetime.now(timezone.utc),
        )

    async def _detect_outliers(self) -> List[Anomaly]:
        if not self._model or not self._vectorizer:
            return []
        logs = await self._fetch_error_logs()
        if not logs:
            return []

        messages: List[str] = []
        log_meta: List[Tuple[str, str, str]] = []
        for log in logs:
            msg = log.get("log", "")
            if not msg:
                continue
            if any(pattern.search(msg) for pattern, _ in ERROR_PATTERNS.values()):
                continue
            k8s = log.get("kubernetes", {})
            messages.append(msg)
            log_meta.append(
                (
                    k8s.get("namespace_name", ""),
                    k8s.get("pod_name", "unknown"),
                    msg,
                )
            )

        if not messages:
            return []

        try:
            tfidf = self._vectorizer.transform(messages)
            scores = self._model.decision_function(tfidf.toarray())
        except Exception as e:
            logger.error("log_insight_analyzer.outlier_score_error", error=str(e))
            return []

        seen: Set[Tuple[str, str]] = set()
        anomalies: List[Anomaly] = []
        for i, score in enumerate(scores):
            if score >= OUTLIER_SCORE_THRESHOLD:
                continue
            ns, pod, msg = log_meta[i]
            dedup_key = (f"{ns}/{pod}", msg[:100])
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            anomalies.append(
                Anomaly(
                    anomaly_id=str(uuid.uuid4()),
                    source="logs_ml",
                    severity=Severity.WARNING,
                    resource_type="pod",
                    resource_name=pod,
                    namespace=ns,
                    description=(f"Unusual log pattern on pod {ns}/{pod}: {msg[:200]}"),
                    score=max(0.0, min(1.0, abs(score))),
                    details={"outlier_score": abs(score), "message": msg},
                    timestamp=datetime.now(timezone.utc),
                )
            )
            if len(anomalies) >= MAX_OUTLIERS_PER_CYCLE:
                break
        return anomalies

    async def _fetch_error_logs(self) -> List[Dict[str, Any]]:
        query = {
            "bool": {
                "must": [{"range": {"@timestamp": {"gte": "now-5m"}}}],
                "should": _ERROR_LOG_SHOULD,
                "minimum_should_match": 1,
            }
        }
        try:
            return await self._storage.query(
                index=self._config.elasticsearch_indices_logs,
                query_body=query,
                size=500,
            )
        except Exception as e:
            logger.error("log_insight_analyzer.fetch_error", error=str(e))
            return []
