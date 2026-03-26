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


def _make_event(reason="OOMKilled", event_type="Warning", name="web-abc", namespace="default"):
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
        mock_apps.list_deployment_for_all_namespaces.return_value = MagicMock(items=[dep])
        mock_apps.list_stateful_set_for_all_namespaces.return_value = MagicMock(items=[])
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
