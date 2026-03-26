import pytest
from unittest.mock import AsyncMock, MagicMock
from src.alerter.webhook import WebhookAlerter
from src.config import Config
from src.models import Anomaly, Severity


@pytest.fixture
def config():
    return Config(
        elasticsearch_url="http://localhost:9200",
        alerter_fallback_webhook_url="http://hooks.example.com/alert",
    )


@pytest.fixture
def alerter(config):
    return WebhookAlerter(config)


@pytest.fixture
def anomaly(sample_timestamp):
    return Anomaly(
        anomaly_id="a-001",
        source="metrics",
        severity=Severity.CRITICAL,
        resource_type="node",
        resource_name="node-1",
        namespace="",
        description="CPU critical",
        score=0.92,
        details={"cpu": 92.0},
        timestamp=sample_timestamp,
    )


class TestWebhookSend:
    @pytest.mark.asyncio
    async def test_send_success(self, alerter, anomaly):
        alerter._http = AsyncMock()
        alerter._http.post = AsyncMock(return_value=MagicMock(status_code=200))
        count = await alerter.send([anomaly])
        assert count == 1

    @pytest.mark.asyncio
    async def test_send_posts_json(self, alerter, anomaly):
        alerter._http = AsyncMock()
        alerter._http.post = AsyncMock(return_value=MagicMock(status_code=200))
        await alerter.send([anomaly])
        call_args = alerter._http.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        assert "anomalies" in payload
        assert len(payload["anomalies"]) == 1
        assert payload["anomalies"][0]["anomaly_id"] == "a-001"

    @pytest.mark.asyncio
    async def test_send_empty(self, alerter):
        count = await alerter.send([])
        assert count == 0

    @pytest.mark.asyncio
    async def test_send_failure(self, alerter, anomaly):
        alerter._http = AsyncMock()
        alerter._http.post = AsyncMock(return_value=MagicMock(status_code=500))
        count = await alerter.send([anomaly])
        assert count == 0

    @pytest.mark.asyncio
    async def test_no_url_configured(self):
        config = Config(
            elasticsearch_url="http://localhost:9200", alerter_fallback_webhook_url=""
        )
        alerter = WebhookAlerter(config)
        count = await alerter.send([MagicMock()])
        assert count == 0


class TestWebhookHealth:
    @pytest.mark.asyncio
    async def test_healthy_with_url(self, alerter):
        alerter._http = AsyncMock()
        assert await alerter.is_healthy() is True

    @pytest.mark.asyncio
    async def test_unhealthy_no_url(self):
        config = Config(
            elasticsearch_url="http://localhost:9200", alerter_fallback_webhook_url=""
        )
        alerter = WebhookAlerter(config)
        assert await alerter.is_healthy() is False
