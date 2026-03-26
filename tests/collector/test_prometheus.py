import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.collector.prometheus import PrometheusCollector
from src.config import Config


@pytest.fixture
def config():
    return Config(
        elasticsearch_url="http://localhost:9200",
        collectors_prometheus_url="http://prometheus:9090",
    )


@pytest.fixture
def collector(config):
    return PrometheusCollector(config)


class TestPrometheusCollectorConnect:
    @pytest.mark.asyncio
    async def test_connect_sets_connected(self, collector):
        with patch("src.collector.prometheus.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=MagicMock(status_code=200))
            mock_client_cls.return_value = mock_client
            await collector.connect()
            assert collector._client is not None


class TestPrometheusCollectorHealthy:
    @pytest.mark.asyncio
    async def test_is_healthy_true(self, collector):
        collector._client = AsyncMock()
        collector._client.get = AsyncMock(return_value=MagicMock(status_code=200))
        assert await collector.is_healthy() is True

    @pytest.mark.asyncio
    async def test_is_healthy_false_no_client(self, collector):
        assert await collector.is_healthy() is False


class TestPrometheusCollectorNodeMetrics:
    @pytest.mark.asyncio
    async def test_collect_node_metrics(self, collector):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "result": [
                    {"metric": {"instance": "node-1"}, "value": [1700000000, "45.2"]},
                ]
            },
        }
        collector._client = AsyncMock()
        collector._client.get = AsyncMock(return_value=mock_response)

        nodes = await collector.collect_node_metrics()
        assert len(nodes) >= 1
        assert nodes[0].node_name == "node-1"

    @pytest.mark.asyncio
    async def test_collect_node_metrics_empty(self, collector):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {"result": []},
        }
        collector._client = AsyncMock()
        collector._client.get = AsyncMock(return_value=mock_response)

        nodes = await collector.collect_node_metrics()
        assert nodes == []


class TestPrometheusCollectorPodMetrics:
    @pytest.mark.asyncio
    async def test_collect_pod_metrics(self, collector):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "result": [
                    {
                        "metric": {
                            "pod": "web-abc123",
                            "namespace": "default",
                            "node": "node-1",
                        },
                        "value": [1700000000, "250"],
                    },
                ]
            },
        }
        collector._client = AsyncMock()
        collector._client.get = AsyncMock(return_value=mock_response)

        pods = await collector.collect_pod_metrics()
        assert len(pods) >= 1
        assert pods[0].pod_name == "web-abc123"

    @pytest.mark.asyncio
    async def test_collect_pod_metrics_filtered_namespace(self, collector):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {"result": []},
        }
        collector._client = AsyncMock()
        collector._client.get = AsyncMock(return_value=mock_response)

        pods = await collector.collect_pod_metrics(namespace="kube-system")
        assert pods == []
        call_args = collector._client.get.call_args
        assert "kube-system" in str(call_args)
