import pytest
from unittest.mock import AsyncMock, MagicMock
from src.alerter.alertmanager import AlertmanagerClient
from src.config import Config
from src.models import Anomaly, Severity


@pytest.fixture
def config():
    return Config(
        elasticsearch_url="http://localhost:9200",
        alerter_alertmanager_url="http://alertmanager:9093",
    )


@pytest.fixture
def client(config):
    return AlertmanagerClient(config)


@pytest.fixture
def critical_anomaly(sample_timestamp):
    return Anomaly(
        anomaly_id="a-001",
        source="metrics",
        severity=Severity.CRITICAL,
        resource_type="node",
        resource_name="node-1",
        namespace="",
        description="CPU usage critical: 92.0%",
        score=0.92,
        details={"cpu_usage_percent": 92.0},
        timestamp=sample_timestamp,
    )


@pytest.fixture
def warning_anomaly(sample_timestamp):
    return Anomaly(
        anomaly_id="a-002",
        source="events",
        severity=Severity.WARNING,
        resource_type="pod",
        resource_name="web-abc",
        namespace="default",
        description="FailedScheduling: 0/3 nodes available",
        score=0.7,
        details={},
        timestamp=sample_timestamp,
    )


class TestAlertmanagerFormat:
    def test_format_alert_critical(self, client, critical_anomaly):
        alerts = client._format_alerts([critical_anomaly])
        assert len(alerts) == 1
        alert = alerts[0]
        assert alert["labels"]["severity"] == "critical"
        assert alert["labels"]["agent"] == "kube-seer"
        assert alert["labels"]["resource_type"] == "node"
        assert alert["labels"]["resource_name"] == "node-1"
        assert "CPU usage critical" in alert["annotations"]["description"]

    def test_format_alert_warning(self, client, warning_anomaly):
        alerts = client._format_alerts([warning_anomaly])
        assert alerts[0]["labels"]["severity"] == "warning"
        assert alerts[0]["labels"]["namespace"] == "default"

    def test_format_alert_includes_source(self, client, critical_anomaly):
        alerts = client._format_alerts([critical_anomaly])
        assert alerts[0]["labels"]["source"] == "metrics"


class TestAlertmanagerSend:
    @pytest.mark.asyncio
    async def test_send_success(self, client, critical_anomaly):
        client._http = AsyncMock()
        client._http.post = AsyncMock(return_value=MagicMock(status_code=200))
        count = await client.send([critical_anomaly])
        assert count == 1
        client._http.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_empty_list(self, client):
        count = await client.send([])
        assert count == 0

    @pytest.mark.asyncio
    async def test_send_failure_returns_zero(self, client, critical_anomaly):
        client._http = AsyncMock()
        client._http.post = AsyncMock(return_value=MagicMock(status_code=500))
        count = await client.send([critical_anomaly])
        assert count == 0


class TestAlertmanagerHealth:
    @pytest.mark.asyncio
    async def test_healthy(self, client):
        client._http = AsyncMock()
        client._http.get = AsyncMock(return_value=MagicMock(status_code=200))
        assert await client.is_healthy() is True

    @pytest.mark.asyncio
    async def test_unhealthy_no_client(self, client):
        assert await client.is_healthy() is False
