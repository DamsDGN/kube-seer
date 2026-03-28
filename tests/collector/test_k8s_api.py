import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from src.collector.k8s_api import KubernetesApiCollector
from src.config import Config


@pytest.fixture
def config():
    return Config(elasticsearch_url="http://localhost:9200")


@pytest.fixture
def collector(config):
    return KubernetesApiCollector(config)


def _make_event(
    reason="OOMKilled", event_type="Warning", name="web-abc", namespace="default"
):
    event = MagicMock()
    event.type = event_type
    event.reason = reason
    event.message = f"Container {reason}"
    event.count = 1
    event.first_timestamp = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    event.last_timestamp = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    event.involved_object = MagicMock()
    event.involved_object.kind = "Pod"
    event.involved_object.name = name
    event.involved_object.namespace = namespace
    return event


def _make_deployment(name="web", namespace="default", desired=3, ready=3):
    dep = MagicMock()
    dep.metadata.name = name
    dep.metadata.namespace = namespace
    dep.spec.replicas = desired
    dep.status.ready_replicas = ready
    dep.status.conditions = []
    return dep


class TestKubernetesApiConnect:
    @pytest.mark.asyncio
    async def test_connect(self, collector):
        with patch("src.collector.k8s_api.config") as mock_config:
            with patch("src.collector.k8s_api.client"):
                mock_config.load_incluster_config = MagicMock()
                await collector.connect()
                assert collector._core_api is not None
                assert collector._apps_api is not None


class TestKubernetesApiEvents:
    @pytest.mark.asyncio
    async def test_collect_events(self, collector):
        mock_core = MagicMock()
        event = _make_event()
        mock_core.list_event_for_all_namespaces.return_value = MagicMock(items=[event])
        collector._core_api = mock_core

        events = await collector.collect_events()
        assert len(events) == 1
        assert events[0].reason == "OOMKilled"
        assert events[0].event_type == "Warning"

    @pytest.mark.asyncio
    async def test_collect_events_namespace(self, collector):
        mock_core = MagicMock()
        event = _make_event()
        mock_core.list_namespaced_event.return_value = MagicMock(items=[event])
        collector._core_api = mock_core

        events = await collector.collect_events(namespace="production")
        assert len(events) == 1
        mock_core.list_namespaced_event.assert_called_once_with(
            "production", field_selector="type=Warning"
        )


class TestKubernetesApiResourceStates:
    @pytest.mark.asyncio
    async def test_collect_resource_states(self, collector):
        mock_apps = MagicMock()
        dep = _make_deployment()
        mock_apps.list_deployment_for_all_namespaces.return_value = MagicMock(
            items=[dep]
        )
        mock_apps.list_stateful_set_for_all_namespaces.return_value = MagicMock(
            items=[]
        )
        mock_apps.list_daemon_set_for_all_namespaces.return_value = MagicMock(items=[])
        collector._apps_api = mock_apps

        mock_batch = MagicMock()
        mock_batch.list_job_for_all_namespaces.return_value = MagicMock(items=[])
        mock_batch.list_cron_job_for_all_namespaces.return_value = MagicMock(items=[])
        collector._batch_api = mock_batch

        states = await collector.collect_resource_states()
        assert len(states) >= 1
        assert states[0].kind == "Deployment"
        assert states[0].name == "web"
        assert states[0].desired_replicas == 3
        assert states[0].ready_replicas == 3


class TestKubernetesApiHealthy:
    @pytest.mark.asyncio
    async def test_is_healthy_true(self, collector):
        mock_core = MagicMock()
        mock_core.list_namespace.return_value = MagicMock()
        collector._core_api = mock_core
        assert await collector.is_healthy() is True

    @pytest.mark.asyncio
    async def test_is_healthy_false(self, collector):
        assert await collector.is_healthy() is False


def _make_pod(name, namespace, cpu_limit=None, memory_limit=None):
    pod = MagicMock()
    pod.metadata.name = name
    pod.metadata.namespace = namespace
    container = MagicMock()
    if cpu_limit or memory_limit:
        container.resources.limits = {}
        if cpu_limit:
            container.resources.limits["cpu"] = cpu_limit
        if memory_limit:
            container.resources.limits["memory"] = memory_limit
    else:
        container.resources.limits = None
    pod.spec.containers = [container]
    return pod


class TestCollectPodLimits:
    @pytest.mark.asyncio
    async def test_pod_with_both_limits(self, collector):
        pod = _make_pod("web-0", "default", cpu_limit="500m", memory_limit="256Mi")
        collector._core_api = MagicMock()
        collector._core_api.list_pod_for_all_namespaces.return_value = MagicMock(
            items=[pod]
        )
        result = await collector.collect_pod_limits()
        assert ("default", "web-0") in result
        cpu_limit, mem_limit = result[("default", "web-0")]
        assert cpu_limit == 500
        assert mem_limit == 268435456

    @pytest.mark.asyncio
    async def test_pod_without_limits(self, collector):
        pod = _make_pod("web-0", "default")
        collector._core_api = MagicMock()
        collector._core_api.list_pod_for_all_namespaces.return_value = MagicMock(
            items=[pod]
        )
        result = await collector.collect_pod_limits()
        cpu_limit, mem_limit = result.get(("default", "web-0"), (None, None))
        assert cpu_limit is None
        assert mem_limit is None

    @pytest.mark.asyncio
    async def test_cpu_whole_number(self, collector):
        pod = _make_pod("db-0", "data", cpu_limit="2", memory_limit="1Gi")
        collector._core_api = MagicMock()
        collector._core_api.list_pod_for_all_namespaces.return_value = MagicMock(
            items=[pod]
        )
        result = await collector.collect_pod_limits()
        cpu_limit, mem_limit = result[("data", "db-0")]
        assert cpu_limit == 2000
        assert mem_limit == 1073741824

    @pytest.mark.asyncio
    async def test_multiple_containers_summed(self, collector):
        pod = MagicMock()
        pod.metadata.name = "multi"
        pod.metadata.namespace = "default"
        c1 = MagicMock()
        c1.resources.limits = {"cpu": "500m", "memory": "256Mi"}
        c2 = MagicMock()
        c2.resources.limits = {"cpu": "500m", "memory": "256Mi"}
        pod.spec.containers = [c1, c2]
        collector._core_api = MagicMock()
        collector._core_api.list_pod_for_all_namespaces.return_value = MagicMock(
            items=[pod]
        )
        result = await collector.collect_pod_limits()
        cpu_limit, mem_limit = result[("default", "multi")]
        assert cpu_limit == 1000
        assert mem_limit == 536870912

    @pytest.mark.asyncio
    async def test_no_core_api(self, collector):
        collector._core_api = None
        result = await collector.collect_pod_limits()
        assert result == {}
