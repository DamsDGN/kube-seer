import structlog
from datetime import datetime, timezone
from typing import List, Optional

from kubernetes import client, config

from src.collector.base import StateCollector
from src.config import Config
from src.models import KubernetesEvent, ResourceState

logger = structlog.get_logger()


class KubernetesApiCollector(StateCollector):
    def __init__(self, config_obj: Config):
        self._config = config_obj
        self._core_api: Optional[client.CoreV1Api] = None
        self._apps_api: Optional[client.AppsV1Api] = None
        self._batch_api: Optional[client.BatchV1Api] = None

    async def connect(self) -> None:
        try:
            config.load_incluster_config()
        except Exception:
            config.load_kube_config()
        self._core_api = client.CoreV1Api()
        self._apps_api = client.AppsV1Api()
        self._batch_api = client.BatchV1Api()
        logger.info("k8s_api_collector.connected")

    async def close(self) -> None:
        self._core_api = None
        self._apps_api = None
        self._batch_api = None

    async def is_healthy(self) -> bool:
        if not self._core_api:
            return False
        try:
            self._core_api.get_api_versions()
            return True
        except Exception:
            return False

    async def collect_events(
        self, namespace: str = ""
    ) -> List[KubernetesEvent]:
        if not self._core_api:
            return []
        try:
            if namespace:
                result = self._core_api.list_namespaced_event(namespace)
            else:
                result = self._core_api.list_event_for_all_namespaces()
        except Exception as e:
            logger.error("k8s_api_collector.events_error", error=str(e))
            return []

        events = []
        for item in result.items:
            events.append(
                KubernetesEvent(
                    event_type=item.type or "Normal",
                    reason=item.reason or "",
                    message=item.message or "",
                    involved_object_kind=item.involved_object.kind or "",
                    involved_object_name=item.involved_object.name or "",
                    involved_object_namespace=item.involved_object.namespace or "",
                    count=item.count or 1,
                    first_timestamp=item.first_timestamp or datetime.now(timezone.utc),
                    last_timestamp=item.last_timestamp or datetime.now(timezone.utc),
                )
            )
        return events

    async def collect_resource_states(
        self, namespace: str = ""
    ) -> List[ResourceState]:
        states: List[ResourceState] = []
        now = datetime.now(timezone.utc)

        states.extend(await self._collect_deployments(namespace, now))
        states.extend(await self._collect_statefulsets(namespace, now))
        states.extend(await self._collect_daemonsets(namespace, now))
        states.extend(await self._collect_jobs(namespace, now))
        states.extend(await self._collect_cronjobs(namespace, now))

        return states

    async def _collect_deployments(
        self, namespace: str, now: datetime
    ) -> List[ResourceState]:
        if not self._apps_api:
            return []
        try:
            if namespace:
                result = self._apps_api.list_namespaced_deployment(namespace)
            else:
                result = self._apps_api.list_deployment_for_all_namespaces()
        except Exception as e:
            logger.error("k8s_api_collector.deployments_error", error=str(e))
            return []

        return [
            ResourceState(
                kind="Deployment",
                name=d.metadata.name,
                namespace=d.metadata.namespace,
                desired_replicas=d.spec.replicas,
                ready_replicas=d.status.ready_replicas or 0,
                conditions={},
                timestamp=now,
            )
            for d in result.items
        ]

    async def _collect_statefulsets(
        self, namespace: str, now: datetime
    ) -> List[ResourceState]:
        if not self._apps_api:
            return []
        try:
            if namespace:
                result = self._apps_api.list_namespaced_stateful_set(namespace)
            else:
                result = self._apps_api.list_stateful_set_for_all_namespaces()
        except Exception as e:
            logger.error("k8s_api_collector.statefulsets_error", error=str(e))
            return []

        return [
            ResourceState(
                kind="StatefulSet",
                name=s.metadata.name,
                namespace=s.metadata.namespace,
                desired_replicas=s.spec.replicas,
                ready_replicas=s.status.ready_replicas or 0,
                conditions={},
                timestamp=now,
            )
            for s in result.items
        ]

    async def _collect_daemonsets(
        self, namespace: str, now: datetime
    ) -> List[ResourceState]:
        if not self._apps_api:
            return []
        try:
            if namespace:
                result = self._apps_api.list_namespaced_daemon_set(namespace)
            else:
                result = self._apps_api.list_daemon_set_for_all_namespaces()
        except Exception as e:
            logger.error("k8s_api_collector.daemonsets_error", error=str(e))
            return []

        return [
            ResourceState(
                kind="DaemonSet",
                name=d.metadata.name,
                namespace=d.metadata.namespace,
                desired_replicas=d.status.desired_number_scheduled,
                ready_replicas=d.status.number_ready or 0,
                conditions={},
                timestamp=now,
            )
            for d in result.items
        ]

    async def _collect_jobs(
        self, namespace: str, now: datetime
    ) -> List[ResourceState]:
        if not self._batch_api:
            return []
        try:
            if namespace:
                result = self._batch_api.list_namespaced_job(namespace)
            else:
                result = self._batch_api.list_job_for_all_namespaces()
        except Exception as e:
            logger.error("k8s_api_collector.jobs_error", error=str(e))
            return []

        return [
            ResourceState(
                kind="Job",
                name=j.metadata.name,
                namespace=j.metadata.namespace,
                desired_replicas=j.spec.completions,
                ready_replicas=j.status.succeeded or 0,
                conditions={},
                timestamp=now,
            )
            for j in result.items
        ]

    async def _collect_cronjobs(
        self, namespace: str, now: datetime
    ) -> List[ResourceState]:
        if not self._batch_api:
            return []
        try:
            if namespace:
                result = self._batch_api.list_namespaced_cron_job(namespace)
            else:
                result = self._batch_api.list_cron_job_for_all_namespaces()
        except Exception as e:
            logger.error("k8s_api_collector.cronjobs_error", error=str(e))
            return []

        return [
            ResourceState(
                kind="CronJob",
                name=c.metadata.name,
                namespace=c.metadata.namespace,
                conditions={
                    "schedule": c.spec.schedule or "",
                    "suspended": c.spec.suspend or False,
                },
                timestamp=now,
            )
            for c in result.items
        ]
