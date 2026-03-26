import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog
from sklearn.cluster import DBSCAN
from sklearn.feature_extraction.text import TfidfVectorizer

from src.analyzer.base import BaseAnalyzer
from src.config import Config
from src.models import Anomaly, Severity
from src.storage.base import BaseStorage

logger = structlog.get_logger()

ERROR_PATTERNS = {
    "oom": (
        re.compile(r"(out of memory|oom|killed process)", re.IGNORECASE),
        Severity.CRITICAL,
    ),
    "connection_refused": (
        re.compile(r"connection refused|ECONNREFUSED", re.IGNORECASE),
        Severity.WARNING,
    ),
    "disk_full": (
        re.compile(r"no space left on device|disk full", re.IGNORECASE),
        Severity.CRITICAL,
    ),
    "permission_denied": (
        re.compile(r"permission denied|EACCES|403 forbidden", re.IGNORECASE),
        Severity.WARNING,
    ),
    "timeout": (
        re.compile(r"timeout|timed out|deadline exceeded", re.IGNORECASE),
        Severity.WARNING,
    ),
    "crash": (
        re.compile(r"FATAL|panic|segfault|core dump", re.IGNORECASE),
        Severity.CRITICAL,
    ),
}

MIN_LOGS_FOR_CLUSTERING = 50


class LogAnalyzer(BaseAnalyzer):
    def __init__(self, config: Config, storage: BaseStorage):
        self._config = config
        self._storage = storage
        self._vectorizer: Optional[TfidfVectorizer] = None
        self._log_buffer: List[str] = []
        self._log_count = 0

    async def analyze(self) -> List[Anomaly]:
        logs = await self._fetch_logs()
        if not logs:
            return []
        anomalies: List[Anomaly] = []
        anomalies.extend(self._check_patterns(logs))
        return anomalies

    async def update_model(self, **kwargs) -> None:
        logs = await self._fetch_logs()
        if not logs:
            return
        messages = [log.get("log", "") for log in logs]
        self._log_buffer.extend(messages)
        self._log_count += len(messages)
        if len(self._log_buffer) >= MIN_LOGS_FOR_CLUSTERING:
            self._train_clustering_model()
            self._log_buffer = self._log_buffer[-self._config.ml_window_size:]

    async def _fetch_logs(self) -> List[Dict[str, Any]]:
        query = {
            "bool": {
                "must": [
                    {"range": {"@timestamp": {"gte": "now-5m"}}},
                ],
                "should": [
                    {"match": {"log": "ERROR"}},
                    {"match": {"log": "FATAL"}},
                    {"match": {"log": "CRITICAL"}},
                    {"match": {"log": "WARN"}},
                    {"match": {"log": "Exception"}},
                ],
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
            logger.error("log_analyzer.fetch_error", error=str(e))
            return []

    def _check_patterns(self, logs: List[Dict[str, Any]]) -> List[Anomaly]:
        anomalies = []
        seen_patterns: Dict[str, int] = {}
        for log in logs:
            message = log.get("log", "")
            k8s = log.get("kubernetes", {})
            pod_name = k8s.get("pod_name", "unknown")
            namespace = k8s.get("namespace_name", "")
            for pattern_name, (pattern, severity) in ERROR_PATTERNS.items():
                if pattern.search(message):
                    key = f"{pattern_name}:{namespace}/{pod_name}"
                    seen_patterns[key] = seen_patterns.get(key, 0) + 1
                    if seen_patterns[key] == 1:
                        anomalies.append(Anomaly(
                            anomaly_id=str(uuid.uuid4()),
                            source="logs",
                            severity=severity,
                            resource_type="pod",
                            resource_name=pod_name,
                            namespace=namespace,
                            description=(
                                f"Log pattern '{pattern_name}' detected: "
                                f"{message[:200]}"
                            ),
                            score=1.0 if severity == Severity.CRITICAL else 0.7,
                            details={
                                "pattern": pattern_name,
                                "sample_message": message[:500],
                            },
                            timestamp=datetime.now(timezone.utc),
                        ))
        return anomalies

    def _train_clustering_model(self) -> None:
        try:
            self._vectorizer = TfidfVectorizer(
                max_features=1000, ngram_range=(1, 2)
            )
            tfidf_matrix = self._vectorizer.fit_transform(self._log_buffer)
            clustering = DBSCAN(eps=0.5, min_samples=3, metric="cosine")
            clustering.fit(tfidf_matrix.toarray())
            n_clusters = len(set(clustering.labels_)) - (
                1 if -1 in clustering.labels_ else 0
            )
            logger.info(
                "log_analyzer.model_trained",
                samples=len(self._log_buffer),
                clusters=n_clusters,
            )
        except Exception as e:
            logger.error("log_analyzer.training_error", error=str(e))
