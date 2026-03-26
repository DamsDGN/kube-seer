import pytest
from unittest.mock import AsyncMock
from src.analyzer.logs import LogAnalyzer
from src.config import Config
from src.storage.base import BaseStorage


@pytest.fixture
def config():
    return Config(elasticsearch_url="http://localhost:9200")


@pytest.fixture
def mock_storage():
    storage = AsyncMock(spec=BaseStorage)
    return storage


@pytest.fixture
def analyzer(config, mock_storage):
    return LogAnalyzer(config, mock_storage)


@pytest.fixture
def error_logs():
    return [
        {
            "timestamp": "2026-01-15T10:30:00Z",
            "kubernetes": {"pod_name": "web-abc", "namespace_name": "default"},
            "log": "ERROR: Connection refused to database at 10.0.0.5:5432",
        },
        {
            "timestamp": "2026-01-15T10:30:01Z",
            "kubernetes": {"pod_name": "web-abc", "namespace_name": "default"},
            "log": "ERROR: Connection refused to database at 10.0.0.5:5432",
        },
        {
            "timestamp": "2026-01-15T10:30:02Z",
            "kubernetes": {"pod_name": "web-abc", "namespace_name": "default"},
            "log": "FATAL: Out of memory - kill process 1234",
        },
    ]


@pytest.fixture
def normal_logs():
    return [
        {
            "timestamp": "2026-01-15T10:30:00Z",
            "kubernetes": {"pod_name": "web-abc", "namespace_name": "default"},
            "log": "INFO: Request processed successfully in 45ms",
        },
    ]


class TestLogAnalyzerPatterns:
    @pytest.mark.asyncio
    async def test_detects_error_logs(self, analyzer, mock_storage, error_logs):
        mock_storage.query = AsyncMock(return_value=error_logs)
        anomalies = await analyzer.analyze()
        error_anomalies = [a for a in anomalies if a.source == "logs"]
        assert len(error_anomalies) >= 1

    @pytest.mark.asyncio
    async def test_detects_oom_in_logs(self, analyzer, mock_storage, error_logs):
        mock_storage.query = AsyncMock(return_value=error_logs)
        anomalies = await analyzer.analyze()
        oom_anomalies = [
            a
            for a in anomalies
            if "memory" in a.description.lower() or "oom" in a.description.lower()
        ]
        assert len(oom_anomalies) >= 1

    @pytest.mark.asyncio
    async def test_no_anomaly_normal_logs(self, analyzer, mock_storage, normal_logs):
        mock_storage.query = AsyncMock(return_value=normal_logs)
        anomalies = await analyzer.analyze()
        assert len(anomalies) == 0

    @pytest.mark.asyncio
    async def test_empty_logs(self, analyzer, mock_storage):
        mock_storage.query = AsyncMock(return_value=[])
        anomalies = await analyzer.analyze()
        assert anomalies == []


class TestLogAnalyzerML:
    @pytest.mark.asyncio
    async def test_update_model(self, analyzer, mock_storage, error_logs):
        mock_storage.query = AsyncMock(return_value=error_logs)
        await analyzer.update_model()
        assert analyzer._log_count > 0

    @pytest.mark.asyncio
    async def test_clustering_with_enough_data(self, analyzer, mock_storage):
        logs = []
        for i in range(60):
            level = "ERROR" if i % 5 == 0 else "INFO"
            logs.append(
                {
                    "timestamp": f"2026-01-15T10:{i:02d}:00Z",
                    "kubernetes": {
                        "pod_name": f"pod-{i % 3}",
                        "namespace_name": "default",
                    },
                    "log": f"{level}: Processing request {i} "
                    f"{'failed' if level == 'ERROR' else 'success'}",
                }
            )
        mock_storage.query = AsyncMock(return_value=logs)
        await analyzer.update_model()
        assert analyzer._vectorizer is not None
