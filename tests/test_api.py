import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport

from src.api.routes import create_app
from src.config import Config


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
