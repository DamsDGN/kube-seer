import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.collector.metrics_server import MetricsServerCollector
from src.config import Config


@pytest.fixture
def config():
    return Config(elasticsearch_url="http://localhost:9200")


@pytest.fixture
def collector(config):
    return MetricsServerCollector(config)


class TestMetricsServerConnect:
    @pytest.mark.asyncio
    async def test_connect_in_cluster(self, collector):
        with patch("src.collector.metrics_server.config") as mock_k8s_config:
            with patch("src.collector.metrics_server.client") as mock_k8s_client:
                mock_k8s_config.load_incluster_config = MagicMock()
                mock_api = MagicMock()
                mock_k8s_client.CustomObjectsApi.return_value = mock_api
                await collector.connect()
                assert collector._api is not None

    @pytest.mark.asyncio
    async def test_connect_fallback_kubeconfig(self, collector):
        with patch("src.collector.metrics_server.config") as mock_k8s_config:
            with patch("src.collector.metrics_server.client") as mock_k8s_client:
                mock_k8s_config.load_incluster_config = MagicMock(
                    side_effect=Exception("not in cluster")
                )
                mock_k8s_config.load_kube_config = MagicMock()
                mock_api = MagicMock()
                mock_k8s_client.CustomObjectsApi.return_value = mock_api
                await collector.connect()
                assert collector._api is not None


class TestMetricsServerNodeMetrics:
    @pytest.mark.asyncio
    async def test_collect_node_metrics(self, collector):
        mock_api = MagicMock()
        mock_api.list_cluster_custom_object.return_value = {
            "items": [
                {
                    "metadata": {"name": "node-1"},
                    "usage": {"cpu": "500m", "memory": "2Gi"},
                    "timestamp": "2026-01-15T10:30:00Z",
                }
            ]
        }
        collector._api = mock_api

        nodes = await collector.collect_node_metrics()
        assert len(nodes) == 1
        assert nodes[0].node_name == "node-1"
        assert nodes[0].cpu_usage_percent > 0


class TestMetricsServerPodMetrics:
    @pytest.mark.asyncio
    async def test_collect_pod_metrics_all_namespaces(self, collector):
        mock_api = MagicMock()
        mock_api.list_cluster_custom_object.return_value = {
            "items": [
                {
                    "metadata": {"name": "web-abc", "namespace": "default"},
                    "containers": [
                        {"name": "web", "usage": {"cpu": "100m", "memory": "128Mi"}}
                    ],
                    "timestamp": "2026-01-15T10:30:00Z",
                }
            ]
        }
        collector._api = mock_api

        pods = await collector.collect_pod_metrics()
        assert len(pods) == 1
        assert pods[0].pod_name == "web-abc"
        assert pods[0].namespace == "default"

    @pytest.mark.asyncio
    async def test_collect_pod_metrics_specific_namespace(self, collector):
        mock_api = MagicMock()
        mock_api.list_namespaced_custom_object.return_value = {
            "items": [
                {
                    "metadata": {"name": "api-xyz", "namespace": "production"},
                    "containers": [
                        {"name": "api", "usage": {"cpu": "200m", "memory": "256Mi"}}
                    ],
                    "timestamp": "2026-01-15T10:30:00Z",
                }
            ]
        }
        collector._api = mock_api

        pods = await collector.collect_pod_metrics(namespace="production")
        assert len(pods) == 1
        assert pods[0].namespace == "production"
