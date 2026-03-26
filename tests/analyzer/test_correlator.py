import pytest
from datetime import datetime, timezone, timedelta

from src.analyzer.correlator import Correlator
from src.config import Config
from src.models import Anomaly, CollectedData, Incident, PodMetrics, Severity


@pytest.fixture
def config():
    return Config(elasticsearch_url="http://localhost:9200")


@pytest.fixture
def correlator(config):
    return Correlator(config)


@pytest.fixture
def ts():
    return datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)


class TestTemporalCorrelation:
    @pytest.mark.asyncio
    async def test_groups_same_resource_anomalies(self, correlator, ts):
        a1 = Anomaly(
            anomaly_id="a-001", source="metrics", severity=Severity.WARNING,
            resource_type="node", resource_name="node-1", namespace="",
            description="CPU warning", score=0.7, details={}, timestamp=ts,
        )
        a2 = Anomaly(
            anomaly_id="a-002", source="metrics", severity=Severity.CRITICAL,
            resource_type="node", resource_name="node-1", namespace="",
            description="Memory critical", score=0.9, details={},
            timestamp=ts + timedelta(seconds=30),
        )
        data = CollectedData(
            node_metrics=[], pod_metrics=[], events=[], resource_states=[],
            collection_timestamp=ts,
        )
        incidents = await correlator.correlate(anomalies=[a1, a2], data=data)
        assert len(incidents) == 1
        assert len(incidents[0].anomalies) == 2
        assert incidents[0].severity == Severity.CRITICAL

    @pytest.mark.asyncio
    async def test_separate_resources_separate_incidents(self, correlator, ts):
        a1 = Anomaly(
            anomaly_id="a-001", source="metrics", severity=Severity.WARNING,
            resource_type="node", resource_name="node-1", namespace="",
            description="CPU warning", score=0.7, details={}, timestamp=ts,
        )
        a2 = Anomaly(
            anomaly_id="a-002", source="metrics", severity=Severity.WARNING,
            resource_type="node", resource_name="node-2", namespace="",
            description="CPU warning", score=0.7, details={}, timestamp=ts,
        )
        data = CollectedData(
            node_metrics=[], pod_metrics=[], events=[], resource_states=[],
            collection_timestamp=ts,
        )
        incidents = await correlator.correlate(anomalies=[a1, a2], data=data)
        assert len(incidents) == 2

    @pytest.mark.asyncio
    async def test_empty_anomalies(self, correlator, ts):
        data = CollectedData(
            node_metrics=[], pod_metrics=[], events=[], resource_states=[],
            collection_timestamp=ts,
        )
        incidents = await correlator.correlate(anomalies=[], data=data)
        assert incidents == []


class TestTopologicalCorrelation:
    @pytest.mark.asyncio
    async def test_correlates_pod_with_node(self, correlator, ts):
        a_node = Anomaly(
            anomaly_id="a-001", source="metrics", severity=Severity.WARNING,
            resource_type="node", resource_name="node-1", namespace="",
            description="Memory warning on node", score=0.7, details={}, timestamp=ts,
        )
        a_pod = Anomaly(
            anomaly_id="a-002", source="events", severity=Severity.CRITICAL,
            resource_type="pod", resource_name="web-abc", namespace="default",
            description="OOMKilled", score=1.0, details={},
            timestamp=ts + timedelta(seconds=10),
        )
        pod = PodMetrics(
            pod_name="web-abc", namespace="default", node_name="node-1",
            cpu_usage_millicores=200, memory_usage_bytes=1000000,
            restart_count=0, status="Running", timestamp=ts,
        )
        data = CollectedData(
            node_metrics=[], pod_metrics=[pod], events=[], resource_states=[],
            collection_timestamp=ts,
        )
        incidents = await correlator.correlate(anomalies=[a_node, a_pod], data=data)
        assert len(incidents) == 1
        assert len(incidents[0].anomalies) == 2
        assert incidents[0].severity == Severity.CRITICAL

    @pytest.mark.asyncio
    async def test_no_topology_link_separate_incidents(self, correlator, ts):
        a_node = Anomaly(
            anomaly_id="a-001", source="metrics", severity=Severity.WARNING,
            resource_type="node", resource_name="node-1", namespace="",
            description="CPU warning", score=0.7, details={}, timestamp=ts,
        )
        a_pod = Anomaly(
            anomaly_id="a-002", source="events", severity=Severity.CRITICAL,
            resource_type="pod", resource_name="web-abc", namespace="default",
            description="OOMKilled", score=1.0, details={}, timestamp=ts,
        )
        pod_on_other_node = PodMetrics(
            pod_name="web-abc", namespace="default", node_name="node-2",
            cpu_usage_millicores=200, memory_usage_bytes=1000000,
            restart_count=0, status="Running", timestamp=ts,
        )
        data = CollectedData(
            node_metrics=[], pod_metrics=[pod_on_other_node], events=[], resource_states=[],
            collection_timestamp=ts,
        )
        incidents = await correlator.correlate(anomalies=[a_node, a_pod], data=data)
        assert len(incidents) == 2


class TestIncidentScoring:
    @pytest.mark.asyncio
    async def test_incident_score_is_max(self, correlator, ts):
        a1 = Anomaly(
            anomaly_id="a-001", source="metrics", severity=Severity.WARNING,
            resource_type="node", resource_name="node-1", namespace="",
            description="CPU warning", score=0.7, details={}, timestamp=ts,
        )
        a2 = Anomaly(
            anomaly_id="a-002", source="metrics", severity=Severity.CRITICAL,
            resource_type="node", resource_name="node-1", namespace="",
            description="Memory critical", score=0.95, details={}, timestamp=ts,
        )
        data = CollectedData(
            node_metrics=[], pod_metrics=[], events=[], resource_states=[],
            collection_timestamp=ts,
        )
        incidents = await correlator.correlate(anomalies=[a1, a2], data=data)
        assert incidents[0].score == 0.95
        assert incidents[0].severity == Severity.CRITICAL
