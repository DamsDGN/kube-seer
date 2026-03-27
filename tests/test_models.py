from src.models import (
    Severity,
    NodeMetrics,
    PodMetrics,
    KubernetesEvent,
    ResourceState,
    CollectedData,
    StoredRecord,
    Anomaly,
    AnalysisResult,
    Incident,
    Prediction,
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


class TestAnomaly:
    def test_creation(self, sample_timestamp):
        anomaly = Anomaly(
            anomaly_id="a-001",
            source="metrics",
            severity=Severity.WARNING,
            resource_type="node",
            resource_name="node-1",
            namespace="",
            description="CPU usage anomaly detected",
            score=0.85,
            details={"cpu_usage_percent": 92.3},
            timestamp=sample_timestamp,
        )
        assert anomaly.anomaly_id == "a-001"
        assert anomaly.severity == Severity.WARNING
        assert anomaly.score == 0.85

    def test_to_dict(self, sample_timestamp):
        anomaly = Anomaly(
            anomaly_id="a-002",
            source="events",
            severity=Severity.CRITICAL,
            resource_type="pod",
            resource_name="web-abc",
            namespace="default",
            description="OOMKilled detected",
            score=1.0,
            details={},
            timestamp=sample_timestamp,
        )
        d = anomaly.model_dump()
        assert d["anomaly_id"] == "a-002"
        assert d["severity"] == 2


class TestIncident:
    def test_creation(self, sample_timestamp):
        anomaly = Anomaly(
            anomaly_id="a-001",
            source="metrics",
            severity=Severity.WARNING,
            resource_type="node",
            resource_name="node-1",
            namespace="",
            description="CPU warning",
            score=0.7,
            details={},
            timestamp=sample_timestamp,
        )
        incident = Incident(
            incident_id="inc-001",
            anomalies=[anomaly],
            severity=Severity.WARNING,
            score=0.7,
            description="CPU warning on node-1",
            resources=["node/node-1"],
            timestamp=sample_timestamp,
        )
        assert incident.incident_id == "inc-001"
        assert len(incident.anomalies) == 1
        assert incident.severity == Severity.WARNING

    def test_multi_anomaly_incident(self, sample_timestamp):
        a1 = Anomaly(
            anomaly_id="a-001",
            source="metrics",
            severity=Severity.WARNING,
            resource_type="node",
            resource_name="node-1",
            namespace="",
            description="Memory warning",
            score=0.7,
            details={},
            timestamp=sample_timestamp,
        )
        a2 = Anomaly(
            anomaly_id="a-002",
            source="events",
            severity=Severity.CRITICAL,
            resource_type="pod",
            resource_name="web-abc",
            namespace="default",
            description="OOMKilled",
            score=1.0,
            details={},
            timestamp=sample_timestamp,
        )
        incident = Incident(
            incident_id="inc-002",
            anomalies=[a1, a2],
            severity=Severity.CRITICAL,
            score=1.0,
            description="Correlated: Memory warning + OOMKilled",
            resources=["node/node-1", "default/pod/web-abc"],
            timestamp=sample_timestamp,
        )
        assert incident.severity == Severity.CRITICAL
        assert len(incident.resources) == 2


class TestAnalysisResult:
    def test_creation(self, sample_timestamp):
        result = AnalysisResult(
            anomalies=[],
            analysis_timestamp=sample_timestamp,
            metrics_analyzed=10,
            logs_analyzed=50,
            events_analyzed=5,
        )
        assert result.anomalies == []
        assert result.metrics_analyzed == 10

    def test_with_anomalies(self, sample_timestamp):
        anomaly = Anomaly(
            anomaly_id="a-001",
            source="metrics",
            severity=Severity.WARNING,
            resource_type="node",
            resource_name="node-1",
            namespace="",
            description="test",
            score=0.5,
            details={},
            timestamp=sample_timestamp,
        )
        result = AnalysisResult(
            anomalies=[anomaly],
            analysis_timestamp=sample_timestamp,
            metrics_analyzed=1,
            logs_analyzed=0,
            events_analyzed=0,
        )
        assert len(result.anomalies) == 1


class TestPrediction:
    def test_creation(self, sample_timestamp):
        pred = Prediction(
            prediction_id="p-001",
            resource_type="node",
            resource_name="node-1",
            namespace="",
            metric_name="disk_usage_percent",
            current_value=82.0,
            predicted_value=100.0,
            threshold=90.0,
            hours_to_threshold=48.5,
            confidence=0.92,
            trend_per_hour=0.165,
            description="Disk saturation estimated in 48h",
            timestamp=sample_timestamp,
        )
        assert pred.prediction_id == "p-001"
        assert pred.hours_to_threshold == 48.5
        assert pred.confidence == 0.92

    def test_to_dict(self, sample_timestamp):
        pred = Prediction(
            prediction_id="p-002",
            resource_type="pod",
            resource_name="db-0",
            namespace="data",
            metric_name="memory_usage_percent",
            current_value=75.0,
            predicted_value=90.0,
            threshold=85.0,
            hours_to_threshold=24.0,
            confidence=0.85,
            trend_per_hour=0.42,
            description="Memory threshold in 24h",
            timestamp=sample_timestamp,
        )
        d = pred.model_dump()
        assert d["metric_name"] == "memory_usage_percent"
        assert d["namespace"] == "data"
