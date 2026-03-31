import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from src.agent import SREAgent
from src.config import Config
from src.models import (
    Anomaly,
    AnalysisResult,
    CollectedData,
    KubernetesEvent,
    NodeMetrics,
    PodMetrics,
    ResourceState,
    Severity,
)


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
        agent._k8s_api.collect_pod_limits = AsyncMock(return_value={})

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


class TestSREAgentPodEnrichment:
    @pytest.mark.asyncio
    async def test_collect_enriches_pods_with_limits(self, agent, sample_timestamp):
        from src.models import PodMetrics, NodeMetrics

        pod = PodMetrics(
            pod_name="web-0",
            namespace="default",
            node_name="node-1",
            cpu_usage_millicores=100,
            memory_usage_bytes=50000000,
            restart_count=0,
            status="Running",
            timestamp=sample_timestamp,
        )
        node = NodeMetrics(
            node_name="node-1",
            cpu_usage_percent=30.0,
            memory_usage_percent=40.0,
            disk_usage_percent=50.0,
            network_rx_bytes=0,
            network_tx_bytes=0,
            conditions={},
            timestamp=sample_timestamp,
        )
        agent._prometheus = AsyncMock()
        agent._prometheus.collect_node_metrics = AsyncMock(return_value=[node])
        agent._prometheus.collect_pod_metrics = AsyncMock(return_value=[pod])
        agent._metrics_server = None
        agent._k8s_api = AsyncMock()
        agent._k8s_api.collect_events = AsyncMock(return_value=[])
        agent._k8s_api.collect_resource_states = AsyncMock(return_value=[])
        agent._k8s_api.collect_pod_limits = AsyncMock(
            return_value={("default", "web-0"): (500, 268435456)}
        )

        data = await agent.collect()
        assert data.pod_metrics[0].cpu_limit_millicores == 500
        assert data.pod_metrics[0].memory_limit_bytes == 268435456


class TestSREAgentAnalyzeTuple:
    @pytest.mark.asyncio
    async def test_analyze_handles_predictor_tuple(self, agent, sample_timestamp):
        from src.models import Anomaly, Severity, CollectedData

        policy_anomaly = Anomaly(
            anomaly_id="a-policy",
            source="policy",
            severity=Severity.WARNING,
            resource_type="pod",
            resource_name="web-0",
            namespace="default",
            description="no memory limit",
            score=0.5,
            details={},
            timestamp=sample_timestamp,
        )
        agent._metrics_analyzer = AsyncMock()
        agent._metrics_analyzer.analyze = AsyncMock(return_value=[])
        agent._event_analyzer = AsyncMock()
        agent._event_analyzer.analyze = AsyncMock(return_value=[])
        agent._log_analyzer = AsyncMock()
        agent._log_analyzer.analyze = AsyncMock(return_value=[])
        agent._correlator = AsyncMock()
        agent._correlator.correlate = AsyncMock(return_value=[])
        agent._predictor = AsyncMock()
        agent._predictor.predict = AsyncMock(return_value=([], [policy_anomaly]))

        data = CollectedData(
            node_metrics=[],
            pod_metrics=[],
            events=[],
            resource_states=[],
            collection_timestamp=sample_timestamp,
        )
        result = await agent.analyze(data)
        assert any(a.anomaly_id == "a-policy" for a in result.anomalies)


def _make_anomaly(
    anomaly_id: str,
    resource_type: str,
    resource_name: str,
    namespace: str = "",
) -> Anomaly:
    return Anomaly(
        anomaly_id=anomaly_id,
        source="test",
        severity=Severity.WARNING,
        resource_type=resource_type,
        resource_name=resource_name,
        namespace=namespace,
        description="test",
        score=0.5,
        details={},
        timestamp=datetime(2026, 3, 31, tzinfo=timezone.utc),
    )


class TestFilterExclusions:
    def _agent(self, **exclusions) -> SREAgent:
        cfg = Config(elasticsearch_url="http://localhost:9200", **exclusions)
        return SREAgent(cfg)

    def test_no_exclusions_keeps_all(self):
        agent = self._agent()
        anomalies = [
            _make_anomaly("a1", "pod", "my-pod", "default"),
            _make_anomaly("a2", "deployment", "my-deploy", "production"),
        ]
        assert agent._filter_exclusions(anomalies) == anomalies

    def test_exclude_namespace(self):
        agent = self._agent(exclusions_namespaces=["kube-system"])
        anomalies = [
            _make_anomaly("a1", "pod", "kube-proxy", "kube-system"),
            _make_anomaly("a2", "pod", "my-app", "default"),
        ]
        result = agent._filter_exclusions(anomalies)
        assert len(result) == 1
        assert result[0].anomaly_id == "a2"

    def test_exclude_deployment_by_name(self):
        agent = self._agent(exclusions_deployments=["grafana"])
        anomalies = [
            _make_anomaly("a1", "deployment", "grafana", "monitoring"),
            _make_anomaly("a2", "deployment", "my-app", "default"),
        ]
        result = agent._filter_exclusions(anomalies)
        assert len(result) == 1
        assert result[0].anomaly_id == "a2"

    def test_exclude_deployment_by_qualified_name(self):
        agent = self._agent(exclusions_deployments=["monitoring/grafana"])
        anomalies = [
            _make_anomaly("a1", "deployment", "grafana", "monitoring"),
            _make_anomaly("a2", "deployment", "grafana", "production"),  # different ns
        ]
        result = agent._filter_exclusions(anomalies)
        assert len(result) == 1
        assert result[0].anomaly_id == "a2"

    def test_exclude_daemonset(self):
        agent = self._agent(exclusions_daemonsets=["kube-system/kube-proxy"])
        anomalies = [
            _make_anomaly("a1", "daemonset", "kube-proxy", "kube-system"),
            _make_anomaly("a2", "daemonset", "fluent-bit", "monitoring"),
        ]
        result = agent._filter_exclusions(anomalies)
        assert len(result) == 1
        assert result[0].anomaly_id == "a2"

    def test_exclude_statefulset(self):
        agent = self._agent(exclusions_statefulsets=["elasticsearch"])
        anomalies = [
            _make_anomaly("a1", "statefulset", "elasticsearch", "elastic-system"),
            _make_anomaly("a2", "statefulset", "my-db", "default"),
        ]
        result = agent._filter_exclusions(anomalies)
        assert len(result) == 1
        assert result[0].anomaly_id == "a2"

    def test_exclude_pod(self):
        agent = self._agent(exclusions_pods=["monitoring/fluent-bit-abc"])
        anomalies = [
            _make_anomaly("a1", "pod", "fluent-bit-abc", "monitoring"),
            _make_anomaly("a2", "pod", "fluent-bit-abc", "other-ns"),  # different ns
        ]
        result = agent._filter_exclusions(anomalies)
        assert len(result) == 1
        assert result[0].anomaly_id == "a2"

    def test_namespace_exclusion_covers_all_resource_types(self):
        agent = self._agent(exclusions_namespaces=["monitoring"])
        anomalies = [
            _make_anomaly("a1", "pod", "fluent-bit", "monitoring"),
            _make_anomaly("a2", "deployment", "grafana", "monitoring"),
            _make_anomaly("a3", "daemonset", "node-exporter", "monitoring"),
            _make_anomaly("a4", "pod", "my-app", "default"),
        ]
        result = agent._filter_exclusions(anomalies)
        assert len(result) == 1
        assert result[0].anomaly_id == "a4"

    def test_csv_string_parsed_correctly(self):
        cfg = Config(
            elasticsearch_url="http://localhost:9200",
            exclusions_namespaces="kube-system,cert-manager",
        )
        assert cfg.exclusions_namespaces == ["kube-system", "cert-manager"]

    def test_empty_string_gives_empty_list(self):
        cfg = Config(
            elasticsearch_url="http://localhost:9200",
            exclusions_namespaces="",
        )
        assert cfg.exclusions_namespaces == []


class TestSREAgentIntelligence:
    @pytest.mark.asyncio
    async def test_intelligence_service_called_in_cycle(self, agent):
        from unittest.mock import AsyncMock

        mock_intel = AsyncMock()
        mock_intel.run = AsyncMock(return_value=None)
        agent._intelligence_service = mock_intel

        # Mock all analyzers to return empty
        agent._metrics_analyzer = AsyncMock()
        agent._metrics_analyzer.analyze = AsyncMock(return_value=[])
        agent._event_analyzer = AsyncMock()
        agent._event_analyzer.analyze = AsyncMock(return_value=[])
        agent._log_analyzer = AsyncMock()
        agent._log_analyzer.analyze = AsyncMock(return_value=[])
        agent._log_insight_analyzer = AsyncMock()
        agent._log_insight_analyzer.analyze = AsyncMock(return_value=[])
        agent._resource_analyzer = AsyncMock()
        agent._resource_analyzer.analyze = AsyncMock(return_value=[])
        agent._correlator = AsyncMock()
        agent._correlator.correlate = AsyncMock(return_value=[])
        agent._predictor = AsyncMock()
        agent._predictor.predict = AsyncMock(return_value=([], []))
        agent._storage.store_bulk = AsyncMock(return_value=0)

        from src.models import CollectedData
        from datetime import datetime, timezone

        data = CollectedData(
            node_metrics=[],
            pod_metrics=[],
            events=[],
            resource_states=[],
            collection_timestamp=datetime(2026, 3, 31, tzinfo=timezone.utc),
        )
        await agent.analyze(data)
        mock_intel.run.assert_called_once()
