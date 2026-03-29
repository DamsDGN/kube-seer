import numpy as np
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.analyzer.log_insights import LogInsightAnalyzer
from src.config import Config
from src.models import Severity
from src.storage.base import BaseStorage


@pytest.fixture
def config():
    return Config(elasticsearch_url="http://localhost:9200")


@pytest.fixture
def mock_storage():
    storage = AsyncMock(spec=BaseStorage)
    storage.query = AsyncMock(return_value=[])
    storage.aggregate = AsyncMock(return_value={})
    return storage


@pytest.fixture
def analyzer(config, mock_storage):
    return LogInsightAnalyzer(config, mock_storage)


def _make_trained_analyzer(config, mock_storage):
    """Return an analyzer with a pre-fitted TF-IDF + IsolationForest model."""
    from sklearn.ensemble import IsolationForest
    from sklearn.feature_extraction.text import TfidfVectorizer

    analyzer = LogInsightAnalyzer(config, mock_storage)
    messages = [f"info processing request {i}" for i in range(60)]
    analyzer._vectorizer = TfidfVectorizer(max_features=500, ngram_range=(1, 2))
    tfidf = analyzer._vectorizer.fit_transform(messages)
    analyzer._model = IsolationForest(
        contamination=0.05, n_estimators=100, random_state=42
    )
    analyzer._model.fit(tfidf.toarray())
    return analyzer


# ── Spike detection ───────────────────────────────────────────────────────────


class TestDetectSpikes:
    @pytest.mark.asyncio
    async def test_no_anomaly_when_ratio_below_3(self, analyzer, mock_storage):
        """Ratio < 3 → no anomaly."""
        mock_storage.aggregate = AsyncMock(
            side_effect=[
                {"by_app": {"buckets": [{"key": "api-gw", "doc_count": 5}]}},
                {"by_app": {"buckets": [{"key": "api-gw", "doc_count": 4}]}},
            ]
        )
        anomalies = await analyzer._detect_spikes()
        assert anomalies == []

    @pytest.mark.asyncio
    async def test_warning_on_3x_ratio(self, analyzer, mock_storage):
        """Ratio >= 3 AND count_N >= 5 → WARNING."""
        mock_storage.aggregate = AsyncMock(
            side_effect=[
                {"by_app": {"buckets": [{"key": "api-gw", "doc_count": 18}]}},
                {"by_app": {"buckets": [{"key": "api-gw", "doc_count": 4}]}},
            ]
        )
        anomalies = await analyzer._detect_spikes()
        assert len(anomalies) == 1
        assert anomalies[0].severity == Severity.WARNING
        assert anomalies[0].source == "logs_ml"
        assert anomalies[0].resource_type == "deployment"
        assert anomalies[0].resource_name == "api-gw"

    @pytest.mark.asyncio
    async def test_critical_on_10x_ratio(self, analyzer, mock_storage):
        """Ratio >= 10 AND count_N >= 5 → CRITICAL."""
        mock_storage.aggregate = AsyncMock(
            side_effect=[
                {"by_app": {"buckets": [{"key": "worker", "doc_count": 47}]}},
                {"by_app": {"buckets": [{"key": "worker", "doc_count": 3}]}},
            ]
        )
        anomalies = await analyzer._detect_spikes()
        assert len(anomalies) == 1
        assert anomalies[0].severity == Severity.CRITICAL

    @pytest.mark.asyncio
    async def test_critical_on_sudden_appearance(self, analyzer, mock_storage):
        """count_N1 == 0 AND count_N >= 10 → CRITICAL."""
        mock_storage.aggregate = AsyncMock(
            side_effect=[
                {"by_app": {"buckets": [{"key": "worker", "doc_count": 23}]}},
                {"by_app": {"buckets": []}},
            ]
        )
        anomalies = await analyzer._detect_spikes()
        assert len(anomalies) == 1
        assert anomalies[0].severity == Severity.CRITICAL

    @pytest.mark.asyncio
    async def test_warning_on_sudden_appearance_below_10(self, analyzer, mock_storage):
        """count_N1 == 0 AND count_N == 7 → WARNING (ratio = 7 >= 3)."""
        mock_storage.aggregate = AsyncMock(
            side_effect=[
                {"by_app": {"buckets": [{"key": "app", "doc_count": 7}]}},
                {"by_app": {"buckets": []}},
            ]
        )
        anomalies = await analyzer._detect_spikes()
        assert len(anomalies) == 1
        assert anomalies[0].severity == Severity.WARNING

    @pytest.mark.asyncio
    async def test_no_anomaly_when_count_below_5(self, analyzer, mock_storage):
        """count_N < 5 → no anomaly regardless of ratio."""
        mock_storage.aggregate = AsyncMock(
            side_effect=[
                {"by_app": {"buckets": [{"key": "api-gw", "doc_count": 4}]}},
                {"by_app": {"buckets": []}},
            ]
        )
        anomalies = await analyzer._detect_spikes()
        assert anomalies == []

    @pytest.mark.asyncio
    async def test_unknown_key_skipped(self, analyzer, mock_storage):
        """__unknown__ (no kubernetes.labels.app) is skipped."""
        mock_storage.aggregate = AsyncMock(
            side_effect=[
                {"by_app": {"buckets": [{"key": "__unknown__", "doc_count": 50}]}},
                {"by_app": {"buckets": []}},
            ]
        )
        anomalies = await analyzer._detect_spikes()
        assert anomalies == []

    @pytest.mark.asyncio
    async def test_description_contains_counts_and_name(self, analyzer, mock_storage):
        """Description must contain previous count, current count, and deployment name."""
        mock_storage.aggregate = AsyncMock(
            side_effect=[
                {"by_app": {"buckets": [{"key": "api-gw", "doc_count": 47}]}},
                {"by_app": {"buckets": [{"key": "api-gw", "doc_count": 3}]}},
            ]
        )
        anomalies = await analyzer._detect_spikes()
        desc = anomalies[0].description
        assert "47" in desc
        assert "3" in desc
        assert "api-gw" in desc

    @pytest.mark.asyncio
    async def test_details_structure(self, analyzer, mock_storage):
        """details must contain previous, current, ratio, window_minutes."""
        mock_storage.aggregate = AsyncMock(
            side_effect=[
                {"by_app": {"buckets": [{"key": "api-gw", "doc_count": 47}]}},
                {"by_app": {"buckets": [{"key": "api-gw", "doc_count": 3}]}},
            ]
        )
        anomalies = await analyzer._detect_spikes()
        d = anomalies[0].details
        assert d["previous"] == 3
        assert d["current"] == 47
        assert d["window_minutes"] == 5
        assert "ratio" in d

    @pytest.mark.asyncio
    async def test_empty_aggregation_no_anomalies(self, analyzer, mock_storage):
        mock_storage.aggregate = AsyncMock(return_value={})
        anomalies = await analyzer._detect_spikes()
        assert anomalies == []

    @pytest.mark.asyncio
    async def test_aggregate_exception_returns_empty(self, analyzer, mock_storage):
        mock_storage.aggregate = AsyncMock(side_effect=Exception("ES down"))
        anomalies = await analyzer._detect_spikes()
        assert anomalies == []


# ── Outlier detection ─────────────────────────────────────────────────────────


class TestDetectOutliers:
    @pytest.mark.asyncio
    async def test_returns_empty_when_model_not_trained(self, analyzer, mock_storage):
        mock_storage.query = AsyncMock(
            return_value=[
                {
                    "log": "weird xzy error 12345",
                    "kubernetes": {"pod_name": "p", "namespace_name": "ns"},
                }
            ]
        )
        anomalies = await analyzer._detect_outliers()
        assert anomalies == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_no_logs(self, config, mock_storage):
        analyzer = _make_trained_analyzer(config, mock_storage)
        mock_storage.query = AsyncMock(return_value=[])
        anomalies = await analyzer._detect_outliers()
        assert anomalies == []

    @pytest.mark.asyncio
    async def test_skips_error_pattern_matches(self, config, mock_storage):
        """Logs matching ERROR_PATTERNS (e.g. connection refused) must not become outliers."""
        analyzer = _make_trained_analyzer(config, mock_storage)
        mock_storage.query = AsyncMock(
            return_value=[
                {
                    "log": "connection refused to database at 10.0.0.5:5432",
                    "kubernetes": {"pod_name": "p", "namespace_name": "ns"},
                }
            ]
        )
        # Even if model says it's an outlier, ERROR_PATTERNS match must filter it out
        analyzer._model.decision_function = MagicMock(return_value=np.array([-0.9]))
        mock_tfidf = MagicMock()
        mock_tfidf.toarray.return_value = np.zeros((1, 500))
        analyzer._vectorizer.transform = MagicMock(return_value=mock_tfidf)
        anomalies = await analyzer._detect_outliers()
        assert anomalies == []

    @pytest.mark.asyncio
    async def test_outlier_anomaly_fields(self, config, mock_storage):
        """Outlier anomaly must have correct source, resource_type, severity, details."""
        analyzer = _make_trained_analyzer(config, mock_storage)
        mock_storage.query = AsyncMock(
            return_value=[
                {
                    "log": "totally weird xzy log 12345",
                    "kubernetes": {"pod_name": "worker-abc", "namespace_name": "prod"},
                }
            ]
        )
        analyzer._model.decision_function = MagicMock(return_value=np.array([-0.5]))
        mock_tfidf = MagicMock()
        mock_tfidf.toarray.return_value = np.zeros((1, 500))
        analyzer._vectorizer.transform = MagicMock(return_value=mock_tfidf)

        anomalies = await analyzer._detect_outliers()
        assert len(anomalies) == 1
        a = anomalies[0]
        assert a.source == "logs_ml"
        assert a.resource_type == "pod"
        assert a.resource_name == "worker-abc"
        assert a.namespace == "prod"
        assert a.severity == Severity.WARNING
        assert "outlier_score" in a.details
        assert "message" in a.details

    @pytest.mark.asyncio
    async def test_deduplication_same_pod_and_message(self, config, mock_storage):
        """Same (namespace/pod, message[:100]) → only one anomaly."""
        analyzer = _make_trained_analyzer(config, mock_storage)
        msg = "totally weird xzy log 12345"
        mock_storage.query = AsyncMock(
            return_value=[
                {"log": msg, "kubernetes": {"pod_name": "p", "namespace_name": "ns"}},
                {"log": msg, "kubernetes": {"pod_name": "p", "namespace_name": "ns"}},
                {"log": msg, "kubernetes": {"pod_name": "p", "namespace_name": "ns"}},
            ]
        )
        analyzer._model.decision_function = MagicMock(
            return_value=np.array([-0.5, -0.5, -0.5])
        )
        mock_tfidf = MagicMock()
        mock_tfidf.toarray.return_value = np.zeros((3, 500))
        analyzer._vectorizer.transform = MagicMock(return_value=mock_tfidf)

        anomalies = await analyzer._detect_outliers()
        assert len(anomalies) == 1

    @pytest.mark.asyncio
    async def test_cap_at_5_per_cycle(self, config, mock_storage):
        """At most 5 outlier anomalies per cycle."""
        analyzer = _make_trained_analyzer(config, mock_storage)
        n = 20
        logs = [
            {
                "log": f"weird xzy log number {i}",
                "kubernetes": {"pod_name": f"pod-{i}", "namespace_name": "ns"},
            }
            for i in range(n)
        ]
        mock_storage.query = AsyncMock(return_value=logs)
        analyzer._model.decision_function = MagicMock(return_value=np.full(n, -0.5))
        mock_tfidf = MagicMock()
        mock_tfidf.toarray.return_value = np.zeros((n, 500))
        analyzer._vectorizer.transform = MagicMock(return_value=mock_tfidf)

        anomalies = await analyzer._detect_outliers()
        assert len(anomalies) <= 5

    @pytest.mark.asyncio
    async def test_score_at_threshold_not_flagged(self, config, mock_storage):
        """Score == -0.1 (exactly at threshold) is not flagged."""
        analyzer = _make_trained_analyzer(config, mock_storage)
        mock_storage.query = AsyncMock(
            return_value=[
                {
                    "log": "weird xzy log 12345",
                    "kubernetes": {"pod_name": "p", "namespace_name": "ns"},
                }
            ]
        )
        analyzer._model.decision_function = MagicMock(return_value=np.array([-0.1]))
        mock_tfidf = MagicMock()
        mock_tfidf.toarray.return_value = np.zeros((1, 500))
        analyzer._vectorizer.transform = MagicMock(return_value=mock_tfidf)

        anomalies = await analyzer._detect_outliers()
        assert anomalies == []


# ── update_model ──────────────────────────────────────────────────────────────


class TestUpdateModel:
    @pytest.mark.asyncio
    async def test_buffer_grows_with_logs(self, analyzer, mock_storage):
        mock_storage.query = AsyncMock(
            return_value=[
                {
                    "log": "ERROR: something failed",
                    "kubernetes": {"pod_name": "p", "namespace_name": "ns"},
                },
                {
                    "log": "WARN: slow query detected",
                    "kubernetes": {"pod_name": "p", "namespace_name": "ns"},
                },
            ]
        )
        await analyzer.update_model()
        assert len(analyzer._message_buffer) == 2

    @pytest.mark.asyncio
    async def test_model_trained_after_50_messages(self, analyzer, mock_storage):
        logs = [
            {
                "log": f"ERROR: error message number {i}",
                "kubernetes": {"pod_name": "p", "namespace_name": "ns"},
            }
            for i in range(60)
        ]
        mock_storage.query = AsyncMock(return_value=logs)
        await analyzer.update_model()
        assert analyzer._model is not None
        assert analyzer._vectorizer is not None

    @pytest.mark.asyncio
    async def test_model_not_trained_below_50_messages(self, analyzer, mock_storage):
        logs = [
            {
                "log": f"ERROR: error {i}",
                "kubernetes": {"pod_name": "p", "namespace_name": "ns"},
            }
            for i in range(30)
        ]
        mock_storage.query = AsyncMock(return_value=logs)
        await analyzer.update_model()
        assert analyzer._model is None

    @pytest.mark.asyncio
    async def test_buffer_capped_at_500(self, analyzer, mock_storage):
        analyzer._message_buffer = [f"old msg {i}" for i in range(490)]
        logs = [
            {
                "log": f"ERROR: overflow message {i}",
                "kubernetes": {"pod_name": "p", "namespace_name": "ns"},
            }
            for i in range(20)
        ]
        mock_storage.query = AsyncMock(return_value=logs)
        await analyzer.update_model()
        assert len(analyzer._message_buffer) <= 500

    @pytest.mark.asyncio
    async def test_empty_logs_does_not_raise(self, analyzer, mock_storage):
        mock_storage.query = AsyncMock(return_value=[])
        await analyzer.update_model()
        assert len(analyzer._message_buffer) == 0


# ── analyze() (integration of spike + outlier) ────────────────────────────────


class TestAnalyze:
    @pytest.mark.asyncio
    async def test_analyze_returns_spike_and_outlier_anomalies(
        self, config, mock_storage
    ):
        """analyze() must combine results from both detectors."""
        analyzer = _make_trained_analyzer(config, mock_storage)

        # Spike: window N has a spike
        mock_storage.aggregate = AsyncMock(
            side_effect=[
                {"by_app": {"buckets": [{"key": "worker", "doc_count": 47}]}},
                {"by_app": {"buckets": [{"key": "worker", "doc_count": 3}]}},
            ]
        )
        # Outlier: one log that is an outlier
        mock_storage.query = AsyncMock(
            return_value=[
                {
                    "log": "weird xzy log 12345",
                    "kubernetes": {"pod_name": "p", "namespace_name": "ns"},
                }
            ]
        )
        analyzer._model.decision_function = MagicMock(return_value=np.array([-0.5]))
        mock_tfidf = MagicMock()
        mock_tfidf.toarray.return_value = np.zeros((1, 500))
        analyzer._vectorizer.transform = MagicMock(return_value=mock_tfidf)

        anomalies = await analyzer.analyze()
        sources = [a.source for a in anomalies]
        assert all(s == "logs_ml" for s in sources)
        resource_types = {a.resource_type for a in anomalies}
        assert "deployment" in resource_types
        assert "pod" in resource_types

    @pytest.mark.asyncio
    async def test_analyze_returns_empty_when_no_data(self, analyzer, mock_storage):
        mock_storage.aggregate = AsyncMock(return_value={})
        mock_storage.query = AsyncMock(return_value=[])
        anomalies = await analyzer.analyze()
        assert anomalies == []
