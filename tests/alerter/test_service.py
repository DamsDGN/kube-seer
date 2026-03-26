import pytest
from unittest.mock import AsyncMock
from datetime import datetime, timezone

from src.alerter.service import AlerterService
from src.config import Config
from src.models import Anomaly, AnalysisResult, Severity


@pytest.fixture
def config():
    return Config(
        elasticsearch_url="http://localhost:9200",
        alerter_alertmanager_enabled=True,
        alerter_alertmanager_url="http://alertmanager:9093",
        alerter_fallback_webhook_enabled=True,
        alerter_fallback_webhook_url="http://hooks.example.com/alert",
    )


@pytest.fixture
def service(config):
    svc = AlerterService(config)
    svc._alertmanager = AsyncMock()
    svc._webhook = AsyncMock()
    return svc


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
        details={},
        timestamp=sample_timestamp,
    )


@pytest.fixture
def info_anomaly(sample_timestamp):
    return Anomaly(
        anomaly_id="a-003",
        source="metrics",
        severity=Severity.INFO,
        resource_type="node",
        resource_name="node-1",
        namespace="",
        description="Low usage",
        score=0.1,
        details={},
        timestamp=sample_timestamp,
    )


class TestAlerterServiceRouting:
    @pytest.mark.asyncio
    async def test_sends_to_alertmanager_primary(self, service, anomaly):
        service._alertmanager.is_healthy = AsyncMock(return_value=True)
        service._alertmanager.send = AsyncMock(return_value=1)
        result = AnalysisResult(
            anomalies=[anomaly], analysis_timestamp=anomaly.timestamp
        )
        await service.send_alerts(result)
        service._alertmanager.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_falls_back_to_webhook(self, service, anomaly):
        service._alertmanager.is_healthy = AsyncMock(return_value=False)
        service._webhook.send = AsyncMock(return_value=1)
        result = AnalysisResult(
            anomalies=[anomaly], analysis_timestamp=anomaly.timestamp
        )
        await service.send_alerts(result)
        service._webhook.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_alerts_on_empty_anomalies(self, service):
        ts = datetime(2026, 1, 15, tzinfo=timezone.utc)
        result = AnalysisResult(anomalies=[], analysis_timestamp=ts)
        await service.send_alerts(result)
        service._alertmanager.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_info_severity(self, service, info_anomaly):
        service._alertmanager.is_healthy = AsyncMock(return_value=True)
        service._alertmanager.send = AsyncMock(return_value=0)
        result = AnalysisResult(
            anomalies=[info_anomaly], analysis_timestamp=info_anomaly.timestamp
        )
        await service.send_alerts(result)
        service._alertmanager.send.assert_not_awaited()


class TestAlerterServiceDedup:
    @pytest.mark.asyncio
    async def test_deduplicates_same_anomaly(self, service, anomaly):
        service._alertmanager.is_healthy = AsyncMock(return_value=True)
        service._alertmanager.send = AsyncMock(return_value=1)
        result = AnalysisResult(
            anomalies=[anomaly], analysis_timestamp=anomaly.timestamp
        )
        await service.send_alerts(result)
        await service.send_alerts(result)
        assert service._alertmanager.send.await_count == 1

    @pytest.mark.asyncio
    async def test_different_anomalies_not_deduped(self, service, sample_timestamp):
        a1 = Anomaly(
            anomaly_id="a-001",
            source="metrics",
            severity=Severity.CRITICAL,
            resource_type="node",
            resource_name="node-1",
            namespace="",
            description="CPU critical",
            score=0.9,
            details={},
            timestamp=sample_timestamp,
        )
        a2 = Anomaly(
            anomaly_id="a-002",
            source="metrics",
            severity=Severity.WARNING,
            resource_type="node",
            resource_name="node-2",
            namespace="",
            description="Memory warning",
            score=0.7,
            details={},
            timestamp=sample_timestamp,
        )
        service._alertmanager.is_healthy = AsyncMock(return_value=True)
        service._alertmanager.send = AsyncMock(return_value=1)
        r1 = AnalysisResult(anomalies=[a1], analysis_timestamp=sample_timestamp)
        r2 = AnalysisResult(anomalies=[a2], analysis_timestamp=sample_timestamp)
        await service.send_alerts(r1)
        await service.send_alerts(r2)
        assert service._alertmanager.send.await_count == 2


class TestAlerterServiceStats:
    @pytest.mark.asyncio
    async def test_stats_tracking(self, service, anomaly):
        service._alertmanager.is_healthy = AsyncMock(return_value=True)
        service._alertmanager.send = AsyncMock(return_value=1)
        result = AnalysisResult(
            anomalies=[anomaly], analysis_timestamp=anomaly.timestamp
        )
        await service.send_alerts(result)
        stats = service.get_stats()
        assert stats["total_sent"] >= 1
        assert stats["alertmanager_sent"] >= 1
