import pytest
from unittest.mock import AsyncMock

from src.agent import SREAgent
from src.config import Config
from src.models import (
    CollectedData,
    NodeMetrics,
    PodMetrics,
    KubernetesEvent,
    ResourceState,
)
from src.models import Anomaly, AnalysisResult, Severity


@pytest.fixture
def config():
    return Config(
        elasticsearch_url="http://localhost:9200",
        collectors_prometheus_enabled=True,
        collectors_metrics_server_enabled=True,
        collectors_k8s_api_enabled=True,
    )


@pytest.fixture
def agent(config):
    a = SREAgent(config)
    a._prometheus = AsyncMock()
    a._metrics_server = AsyncMock()
    a._k8s_api = AsyncMock()
    a._storage = AsyncMock()
    return a


class TestSREAgentInit:
    def test_init(self, config):
        agent = SREAgent(config)
        assert agent._config is config
        assert agent._running is False


class TestSREAgentCollect:
    @pytest.mark.asyncio
    async def test_collect_aggregates_all_sources(self, agent, sample_timestamp):
        node = NodeMetrics(
            node_name="node-1",
            cpu_usage_percent=45.0,
            memory_usage_percent=60.0,
            disk_usage_percent=30.0,
            network_rx_bytes=0,
            network_tx_bytes=0,
            conditions={},
            timestamp=sample_timestamp,
        )
        pod = PodMetrics(
            pod_name="web-abc",
            namespace="default",
            node_name="node-1",
            cpu_usage_millicores=250,
            memory_usage_bytes=134217728,
            restart_count=0,
            status="Running",
            timestamp=sample_timestamp,
        )
        event = KubernetesEvent(
            event_type="Warning",
            reason="OOMKilled",
            message="OOM",
            involved_object_kind="Pod",
            involved_object_name="web-abc",
            involved_object_namespace="default",
            count=1,
            first_timestamp=sample_timestamp,
            last_timestamp=sample_timestamp,
        )
        state = ResourceState(
            kind="Deployment",
            name="web",
            namespace="default",
            desired_replicas=3,
            ready_replicas=3,
            conditions={},
            timestamp=sample_timestamp,
        )

        agent._prometheus.collect_node_metrics = AsyncMock(return_value=[node])
        agent._prometheus.collect_pod_metrics = AsyncMock(return_value=[pod])
        agent._metrics_server.collect_node_metrics = AsyncMock(return_value=[])
        agent._metrics_server.collect_pod_metrics = AsyncMock(return_value=[])
        agent._k8s_api.collect_events = AsyncMock(return_value=[event])
        agent._k8s_api.collect_resource_states = AsyncMock(return_value=[state])

        data = await agent.collect()
        assert len(data.node_metrics) == 1
        assert len(data.pod_metrics) == 1
        assert len(data.events) == 1
        assert len(data.resource_states) == 1

    @pytest.mark.asyncio
    async def test_collect_handles_disabled_collectors(self, config):
        config_disabled = Config(
            elasticsearch_url="http://localhost:9200",
            collectors_prometheus_enabled=False,
            collectors_metrics_server_enabled=False,
            collectors_k8s_api_enabled=False,
        )
        agent = SREAgent(config_disabled)
        data = await agent.collect()
        assert data.node_metrics == []
        assert data.pod_metrics == []
        assert data.events == []
        assert data.resource_states == []


class TestSREAgentStore:
    @pytest.mark.asyncio
    async def test_store_writes_to_elasticsearch(self, agent, sample_timestamp):
        data = CollectedData(
            node_metrics=[
                NodeMetrics(
                    node_name="node-1",
                    cpu_usage_percent=45.0,
                    memory_usage_percent=60.0,
                    disk_usage_percent=30.0,
                    network_rx_bytes=0,
                    network_tx_bytes=0,
                    conditions={},
                    timestamp=sample_timestamp,
                )
            ],
            pod_metrics=[],
            events=[],
            resource_states=[],
            collection_timestamp=sample_timestamp,
        )
        agent._storage.store_bulk = AsyncMock(return_value=1)

        await agent.store(data)
        agent._storage.store_bulk.assert_called()


class TestSREAgentCycle:
    @pytest.mark.asyncio
    async def test_run_cycle(self, agent, sample_timestamp):
        agent.collect = AsyncMock(
            return_value=CollectedData(
                node_metrics=[],
                pod_metrics=[],
                events=[],
                resource_states=[],
                collection_timestamp=sample_timestamp,
            )
        )
        agent.store = AsyncMock()

        await agent.run_cycle()
        agent.collect.assert_awaited_once()
        agent.store.assert_awaited_once()


class TestSREAgentAnalyze:
    @pytest.mark.asyncio
    async def test_analyze_returns_result(self, agent, sample_timestamp):
        agent._metrics_analyzer = AsyncMock()
        agent._metrics_analyzer.analyze = AsyncMock(return_value=[])
        agent._event_analyzer = AsyncMock()
        agent._event_analyzer.analyze = AsyncMock(return_value=[])
        agent._log_analyzer = AsyncMock()
        agent._log_analyzer.analyze = AsyncMock(return_value=[])

        data = CollectedData(
            node_metrics=[],
            pod_metrics=[],
            events=[],
            resource_states=[],
            collection_timestamp=sample_timestamp,
        )
        result = await agent.analyze(data)
        assert isinstance(result, AnalysisResult)
        assert result.anomalies == []

    @pytest.mark.asyncio
    async def test_analyze_aggregates_anomalies(self, agent, sample_timestamp):
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
        agent._metrics_analyzer = AsyncMock()
        agent._metrics_analyzer.analyze = AsyncMock(return_value=[anomaly])
        agent._event_analyzer = AsyncMock()
        agent._event_analyzer.analyze = AsyncMock(return_value=[])
        agent._log_analyzer = AsyncMock()
        agent._log_analyzer.analyze = AsyncMock(return_value=[])

        data = CollectedData(
            node_metrics=[],
            pod_metrics=[],
            events=[],
            resource_states=[],
            collection_timestamp=sample_timestamp,
        )
        result = await agent.analyze(data)
        assert len(result.anomalies) == 1
        assert result.anomalies[0].anomaly_id == "a-001"


class TestSREAgentCycleWithAnalysis:
    @pytest.mark.asyncio
    async def test_run_cycle_includes_analyze(self, agent, sample_timestamp):
        agent.collect = AsyncMock(
            return_value=CollectedData(
                node_metrics=[],
                pod_metrics=[],
                events=[],
                resource_states=[],
                collection_timestamp=sample_timestamp,
            )
        )
        agent.analyze = AsyncMock(
            return_value=AnalysisResult(
                anomalies=[],
                analysis_timestamp=sample_timestamp,
            )
        )
        agent.store = AsyncMock()
        agent.store_anomalies = AsyncMock()
        agent.update_models = AsyncMock()

        await agent.run_cycle()
        agent.collect.assert_awaited_once()
        agent.analyze.assert_awaited_once()
        agent.store.assert_awaited_once()


class TestSREAgentCorrelation:
    @pytest.mark.asyncio
    async def test_analyze_includes_correlation(self, agent, sample_timestamp):
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
        agent._metrics_analyzer = AsyncMock()
        agent._metrics_analyzer.analyze = AsyncMock(return_value=[anomaly])
        agent._event_analyzer = AsyncMock()
        agent._event_analyzer.analyze = AsyncMock(return_value=[])
        agent._log_analyzer = AsyncMock()
        agent._log_analyzer.analyze = AsyncMock(return_value=[])

        data = CollectedData(
            node_metrics=[],
            pod_metrics=[],
            events=[],
            resource_states=[],
            collection_timestamp=sample_timestamp,
        )
        result = await agent.analyze(data)
        assert len(result.incidents) >= 1
        assert result.incidents[0].anomalies[0].anomaly_id == "a-001"


class TestSREAgentAlerts:
    @pytest.mark.asyncio
    async def test_run_cycle_sends_alerts(self, agent, sample_timestamp):
        agent.collect = AsyncMock(
            return_value=CollectedData(
                node_metrics=[],
                pod_metrics=[],
                events=[],
                resource_states=[],
                collection_timestamp=sample_timestamp,
            )
        )
        agent.analyze = AsyncMock(
            return_value=AnalysisResult(
                anomalies=[], analysis_timestamp=sample_timestamp
            )
        )
        agent.store = AsyncMock()
        agent.store_anomalies = AsyncMock()
        agent.update_models = AsyncMock()
        agent._alerter = AsyncMock()
        agent._alerter.send_alerts = AsyncMock()

        await agent.run_cycle()
        agent._alerter.send_alerts.assert_awaited_once()


class TestSREAgentPrediction:
    @pytest.mark.asyncio
    async def test_run_cycle_includes_predictions(self, agent, sample_timestamp):
        agent.collect = AsyncMock(
            return_value=CollectedData(
                node_metrics=[],
                pod_metrics=[],
                events=[],
                resource_states=[],
                collection_timestamp=sample_timestamp,
            )
        )
        agent.analyze = AsyncMock(
            return_value=AnalysisResult(
                anomalies=[],
                incidents=[],
                predictions=[],
                analysis_timestamp=sample_timestamp,
            )
        )
        agent.store = AsyncMock()
        agent.store_anomalies = AsyncMock()
        agent.update_models = AsyncMock()
        agent._alerter = AsyncMock()
        agent._alerter.send_alerts = AsyncMock()

        await agent.run_cycle()
        agent.analyze.assert_awaited_once()
