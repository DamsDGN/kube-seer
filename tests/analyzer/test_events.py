import pytest
from src.analyzer.events import EventAnalyzer
from src.config import Config
from src.models import KubernetesEvent, Severity


@pytest.fixture
def config():
    return Config(elasticsearch_url="http://localhost:9200")


@pytest.fixture
def analyzer(config):
    return EventAnalyzer(config)


@pytest.fixture
def oom_event(sample_timestamp):
    return KubernetesEvent(
        event_type="Warning",
        reason="OOMKilled",
        message="Container web killed due to OOM",
        involved_object_kind="Pod",
        involved_object_name="web-abc",
        involved_object_namespace="default",
        count=1,
        first_timestamp=sample_timestamp,
        last_timestamp=sample_timestamp,
    )


@pytest.fixture
def normal_event(sample_timestamp):
    return KubernetesEvent(
        event_type="Normal",
        reason="Scheduled",
        message="Successfully assigned pod",
        involved_object_kind="Pod",
        involved_object_name="web-abc",
        involved_object_namespace="default",
        count=1,
        first_timestamp=sample_timestamp,
        last_timestamp=sample_timestamp,
    )


class TestEventAnalyzerPatterns:
    @pytest.mark.asyncio
    async def test_detects_oom_killed(self, analyzer, oom_event):
        anomalies = await analyzer.analyze(events=[oom_event])
        assert len(anomalies) >= 1
        assert anomalies[0].severity == Severity.CRITICAL
        assert "OOMKilled" in anomalies[0].description

    @pytest.mark.asyncio
    async def test_no_anomaly_normal_event(self, analyzer, normal_event):
        anomalies = await analyzer.analyze(events=[normal_event])
        assert len(anomalies) == 0

    @pytest.mark.asyncio
    async def test_detects_failed_scheduling(self, analyzer, sample_timestamp):
        event = KubernetesEvent(
            event_type="Warning",
            reason="FailedScheduling",
            message="0/3 nodes are available",
            involved_object_kind="Pod",
            involved_object_name="api-xyz",
            involved_object_namespace="production",
            count=5,
            first_timestamp=sample_timestamp,
            last_timestamp=sample_timestamp,
        )
        anomalies = await analyzer.analyze(events=[event])
        assert len(anomalies) >= 1
        assert anomalies[0].resource_name == "api-xyz"

    @pytest.mark.asyncio
    async def test_detects_failed_mount(self, analyzer, sample_timestamp):
        event = KubernetesEvent(
            event_type="Warning",
            reason="FailedMount",
            message="Unable to attach volume",
            involved_object_kind="Pod",
            involved_object_name="db-0",
            involved_object_namespace="data",
            count=1,
            first_timestamp=sample_timestamp,
            last_timestamp=sample_timestamp,
        )
        anomalies = await analyzer.analyze(events=[event])
        assert len(anomalies) >= 1


class TestEventAnalyzerFrequency:
    @pytest.mark.asyncio
    async def test_detects_event_burst(self, analyzer, sample_timestamp):
        events = []
        for i in range(20):
            events.append(
                KubernetesEvent(
                    event_type="Warning",
                    reason="BackOff",
                    message=f"Back-off restarting failed container {i}",
                    involved_object_kind="Pod",
                    involved_object_name="worker-fail",
                    involved_object_namespace="default",
                    count=1,
                    first_timestamp=sample_timestamp,
                    last_timestamp=sample_timestamp,
                )
            )
        anomalies = await analyzer.analyze(events=events)
        burst_anomalies = [a for a in anomalies if "burst" in a.description.lower()]
        assert len(burst_anomalies) >= 1

    @pytest.mark.asyncio
    async def test_empty_events(self, analyzer):
        anomalies = await analyzer.analyze(events=[])
        assert anomalies == []
