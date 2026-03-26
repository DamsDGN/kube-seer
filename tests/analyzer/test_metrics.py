import pytest
from src.analyzer.metrics import MetricsAnalyzer
from src.config import Config
from src.models import NodeMetrics, PodMetrics, Severity


@pytest.fixture
def config():
    return Config(
        elasticsearch_url="http://localhost:9200",
        thresholds_cpu_warning=70.0,
        thresholds_cpu_critical=85.0,
        thresholds_memory_warning=70.0,
        thresholds_memory_critical=85.0,
        thresholds_disk_warning=80.0,
        thresholds_disk_critical=90.0,
    )


@pytest.fixture
def analyzer(config):
    return MetricsAnalyzer(config)


@pytest.fixture
def normal_node(sample_timestamp):
    return NodeMetrics(
        node_name="node-1",
        cpu_usage_percent=30.0,
        memory_usage_percent=40.0,
        disk_usage_percent=25.0,
        network_rx_bytes=1000,
        network_tx_bytes=500,
        conditions={},
        timestamp=sample_timestamp,
    )


@pytest.fixture
def high_cpu_node(sample_timestamp):
    return NodeMetrics(
        node_name="node-2",
        cpu_usage_percent=92.0,
        memory_usage_percent=40.0,
        disk_usage_percent=25.0,
        network_rx_bytes=1000,
        network_tx_bytes=500,
        conditions={},
        timestamp=sample_timestamp,
    )


@pytest.fixture
def normal_pod(sample_timestamp):
    return PodMetrics(
        pod_name="web-abc",
        namespace="default",
        node_name="node-1",
        cpu_usage_millicores=100,
        memory_usage_bytes=67108864,
        restart_count=0,
        status="Running",
        timestamp=sample_timestamp,
    )


@pytest.fixture
def crashing_pod(sample_timestamp):
    return PodMetrics(
        pod_name="worker-xyz",
        namespace="default",
        node_name="node-1",
        cpu_usage_millicores=50,
        memory_usage_bytes=67108864,
        restart_count=15,
        status="CrashLoopBackOff",
        timestamp=sample_timestamp,
    )


class TestMetricsAnalyzerThresholds:
    @pytest.mark.asyncio
    async def test_no_anomaly_normal_node(self, analyzer, normal_node):
        anomalies = await analyzer.analyze(node_metrics=[normal_node], pod_metrics=[])
        assert len(anomalies) == 0

    @pytest.mark.asyncio
    async def test_detects_high_cpu_node(self, analyzer, high_cpu_node):
        anomalies = await analyzer.analyze(node_metrics=[high_cpu_node], pod_metrics=[])
        cpu_anomalies = [a for a in anomalies if "CPU" in a.description]
        assert len(cpu_anomalies) >= 1
        assert cpu_anomalies[0].severity == Severity.CRITICAL
        assert cpu_anomalies[0].resource_name == "node-2"

    @pytest.mark.asyncio
    async def test_detects_crashing_pod(self, analyzer, crashing_pod):
        anomalies = await analyzer.analyze(node_metrics=[], pod_metrics=[crashing_pod])
        restart_anomalies = [a for a in anomalies if "restart" in a.description.lower()]
        assert len(restart_anomalies) >= 1
        assert restart_anomalies[0].severity == Severity.CRITICAL

    @pytest.mark.asyncio
    async def test_detects_crashloop_status(self, analyzer, crashing_pod):
        anomalies = await analyzer.analyze(node_metrics=[], pod_metrics=[crashing_pod])
        status_anomalies = [a for a in anomalies if "CrashLoop" in a.description]
        assert len(status_anomalies) >= 1


class TestMetricsAnalyzerML:
    @pytest.mark.asyncio
    async def test_update_model_stores_data(self, analyzer, normal_node):
        await analyzer.update_model(node_metrics=[normal_node], pod_metrics=[])
        assert analyzer._node_samples_count > 0

    @pytest.mark.asyncio
    async def test_model_trains_after_enough_samples(self, analyzer, sample_timestamp):
        nodes = []
        for i in range(50):
            nodes.append(
                NodeMetrics(
                    node_name=f"node-{i}",
                    cpu_usage_percent=30.0 + (i % 10),
                    memory_usage_percent=40.0 + (i % 8),
                    disk_usage_percent=20.0,
                    network_rx_bytes=1000,
                    network_tx_bytes=500,
                    conditions={},
                    timestamp=sample_timestamp,
                )
            )
        await analyzer.update_model(node_metrics=nodes, pod_metrics=[])
        assert analyzer._node_model is not None

    @pytest.mark.asyncio
    async def test_empty_input_returns_no_anomalies(self, analyzer):
        anomalies = await analyzer.analyze(node_metrics=[], pod_metrics=[])
        assert anomalies == []
