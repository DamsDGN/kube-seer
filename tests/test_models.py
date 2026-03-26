import pytest
from datetime import datetime, timezone
from src.models import (
    Severity,
    NodeMetrics,
    PodMetrics,
    KubernetesEvent,
    ResourceState,
    CollectedData,
    StoredRecord,
)


class TestSeverity:
    def test_ordering(self):
        assert Severity.INFO < Severity.WARNING < Severity.CRITICAL


class TestNodeMetrics:
    def test_creation(self, sample_timestamp):
        node = NodeMetrics(
            node_name="node-1",
            cpu_usage_percent=45.2,
            memory_usage_percent=62.1,
            disk_usage_percent=30.0,
            network_rx_bytes=1000000,
            network_tx_bytes=500000,
            conditions={"Ready": True, "DiskPressure": False},
            timestamp=sample_timestamp,
        )
        assert node.node_name == "node-1"
        assert node.cpu_usage_percent == 45.2
        assert node.conditions["Ready"] is True

    def test_to_dict(self, sample_timestamp):
        node = NodeMetrics(
            node_name="node-1",
            cpu_usage_percent=45.2,
            memory_usage_percent=62.1,
            disk_usage_percent=30.0,
            network_rx_bytes=1000000,
            network_tx_bytes=500000,
            conditions={},
            timestamp=sample_timestamp,
        )
        d = node.model_dump()
        assert d["node_name"] == "node-1"
        assert "timestamp" in d


class TestPodMetrics:
    def test_creation(self, sample_timestamp):
        pod = PodMetrics(
            pod_name="web-abc123",
            namespace="default",
            node_name="node-1",
            cpu_usage_millicores=250,
            memory_usage_bytes=134217728,
            restart_count=0,
            status="Running",
            timestamp=sample_timestamp,
        )
        assert pod.pod_name == "web-abc123"
        assert pod.cpu_usage_millicores == 250
        assert pod.restart_count == 0


class TestKubernetesEvent:
    def test_creation(self, sample_timestamp):
        event = KubernetesEvent(
            event_type="Warning",
            reason="OOMKilled",
            message="Container killed due to OOM",
            involved_object_kind="Pod",
            involved_object_name="web-abc123",
            involved_object_namespace="default",
            count=1,
            first_timestamp=sample_timestamp,
            last_timestamp=sample_timestamp,
        )
        assert event.event_type == "Warning"
        assert event.reason == "OOMKilled"


class TestResourceState:
    def test_creation(self, sample_timestamp):
        state = ResourceState(
            kind="Deployment",
            name="web",
            namespace="default",
            desired_replicas=3,
            ready_replicas=3,
            conditions={"Available": True},
            timestamp=sample_timestamp,
        )
        assert state.kind == "Deployment"
        assert state.desired_replicas == 3


class TestCollectedData:
    def test_creation(self, sample_timestamp):
        data = CollectedData(
            node_metrics=[],
            pod_metrics=[],
            events=[],
            resource_states=[],
            collection_timestamp=sample_timestamp,
        )
        assert data.node_metrics == []
        assert data.collection_timestamp == sample_timestamp


class TestStoredRecord:
    def test_creation(self, sample_timestamp):
        record = StoredRecord(
            record_type="node_metrics",
            data={"node_name": "node-1", "cpu": 45.2},
            timestamp=sample_timestamp,
            cluster_name="prod-01",
        )
        assert record.record_type == "node_metrics"
        assert record.cluster_name == "prod-01"
