import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport

from src.api.routes import create_app
from src.config import Config
from src.models import AnalysisResult


@pytest.fixture
def config():
    return Config(elasticsearch_url="http://localhost:9200")


@pytest.fixture
def mock_agent():
    agent = AsyncMock()
    agent._config = Config(elasticsearch_url="http://localhost:9200")
    agent._storage = AsyncMock()
    agent._storage.is_healthy = AsyncMock(return_value=True)
    agent._prometheus = AsyncMock()
    agent._prometheus.is_healthy = AsyncMock(return_value=True)
    agent._metrics_server = AsyncMock()
    agent._metrics_server.is_healthy = AsyncMock(return_value=True)
    agent._k8s_api = AsyncMock()
    agent._k8s_api.is_healthy = AsyncMock(return_value=True)
    agent._running = True
    return agent


@pytest.fixture
def app(config, mock_agent):
    return create_app(config, mock_agent)


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


class TestReadyEndpoint:
    @pytest.mark.asyncio
    async def test_ready_all_healthy(self, client):
        resp = await client.get("/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ready"] is True

    @pytest.mark.asyncio
    async def test_ready_es_unhealthy(self, client, mock_agent):
        mock_agent._storage.is_healthy = AsyncMock(return_value=False)
        resp = await client.get("/ready")
        assert resp.status_code == 503
        data = resp.json()
        assert data["ready"] is False


class TestStatusEndpoint:
    @pytest.mark.asyncio
    async def test_status(self, client):
        resp = await client.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "elasticsearch" in data
        assert "prometheus" in data
        assert "agent_running" in data


class TestConfigEndpoint:
    @pytest.mark.asyncio
    async def test_config_no_secrets(self, client):
        resp = await client.get("/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "elasticsearch_password" not in data
        assert "intelligence_api_key" not in data
        assert "elasticsearch_url" in data


class TestAnomaliesEndpoint:
    @pytest.mark.asyncio
    async def test_anomalies_empty(self, client, mock_agent):
        mock_agent._storage.query = AsyncMock(return_value=[])
        resp = await client.get("/anomalies")
        assert resp.status_code == 200
        assert resp.json()["anomalies"] == []

    @pytest.mark.asyncio
    async def test_anomalies_with_results(self, client, mock_agent):
        mock_agent._storage.query = AsyncMock(return_value=[
            {
                "record_type": "anomaly",
                "data": {
                    "anomaly_id": "a-001",
                    "source": "metrics",
                    "severity": 1,
                    "resource_type": "node",
                    "resource_name": "node-1",
                    "namespace": "",
                    "description": "CPU high",
                    "score": 0.85,
                    "details": {},
                    "timestamp": "2026-01-15T10:30:00Z",
                },
                "timestamp": "2026-01-15T10:30:00Z",
                "cluster_name": "",
            }
        ])
        resp = await client.get("/anomalies")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["anomalies"]) == 1
        assert data["anomalies"][0]["data"]["anomaly_id"] == "a-001"

    @pytest.mark.asyncio
    async def test_anomalies_filter_severity(self, client, mock_agent):
        mock_agent._storage.query = AsyncMock(return_value=[])
        resp = await client.get("/anomalies?severity=critical")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_anomalies_filter_namespace(self, client, mock_agent):
        mock_agent._storage.query = AsyncMock(return_value=[])
        resp = await client.get("/anomalies?namespace=production")
        assert resp.status_code == 200


class TestAnalyzeEndpoint:
    @pytest.mark.asyncio
    async def test_trigger_manual_analysis(self, client, mock_agent):
        mock_agent.run_cycle = AsyncMock()
        mock_agent._last_analysis = AnalysisResult(
            anomalies=[],
            analysis_timestamp=datetime(2026, 1, 15, 10, 30, tzinfo=timezone.utc),
            metrics_analyzed=5,
            events_analyzed=3,
        )
        resp = await client.post("/analyze")
        assert resp.status_code == 200
        mock_agent.run_cycle.assert_awaited_once()


class TestAlertStatsEndpoint:
    @pytest.mark.asyncio
    async def test_alert_stats(self, client, mock_agent):
        mock_agent._alerter = MagicMock()
        mock_agent._alerter.get_stats.return_value = {
            "total_sent": 5,
            "alertmanager_sent": 3,
            "webhook_sent": 2,
            "deduped": 1,
            "skipped_info": 0,
        }
        resp = await client.get("/alerts/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_sent"] == 5
        assert data["alertmanager_sent"] == 3
