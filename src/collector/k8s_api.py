import asyncio
import structlog
from datetime import datetime, timezone
from typing import List, Optional

from kubernetes import client, config

from src.collector.base import StateCollector
from src.config import Config
from src.models import KubernetesEvent, ResourceState

logger = structlog.get_logger()


def _parse_cpu_millicores(cpu_str: str) -> int:
    """Parse Kubernetes CPU quantity string to millicores."""
    cpu_str = cpu_str.strip()
    if cpu_str.endswith("m"):
        return int(cpu_str[:-1])
    return int(float(cpu_str) * 1000)


def _parse_memory_bytes(mem_str: str) -> int:
    """Parse Kubernetes memory quantity string to bytes."""
    mem_str = mem_str.strip()
    suffixes = [
        ("Ki", 1024),
        ("Mi", 1024**2),
        ("Gi", 1024**3),
        ("Ti", 1024**4),
        ("K", 1000),
        ("M", 1000**2),
        ("G", 1000**3),
        ("T", 1000**4),
    ]
    for suffix, multiplier in suffixes:
        if mem_str.endswith(suffix):
            return int(mem_str[: -len(suffix)]) * multiplier
    return int(mem_str)


class KubernetesApiCollector(StateCollector):
    def __init__(self, config_obj: Config):
        self._config = config_obj
        self._core_api: Optional[client.CoreV1Api] = None
        self._apps_api: Optional[client.AppsV1Api] = None
        self._batch_api: Optional[client.BatchV1Api] = None
        self._autoscaling_api: Optional[client.AutoscalingV1Api] = None
        self._networking_api: Optional[client.NetworkingV1Api] = None
        self._policy_api: Optional[client.PolicyV1Api] = None

    async def connect(self) -> None:
        try:
            config.load_incluster_config()
        except Exception:
            config.load_kube_config()
        self._core_api = client.CoreV1Api()
        self._apps_api = client.AppsV1Api()
        self._batch_api = client.BatchV1Api()
        self._autoscaling_api = client.AutoscalingV1Api()
        self._networking_api = client.NetworkingV1Api()
        self._policy_api = client.PolicyV1Api()
        logger.info("k8s_api_collector.connected")

    async def close(self) -> None:
        self._core_api = None
        self._apps_api = None
        self._batch_api = None
        self._autoscaling_api = None
        self._networking_api = None
        self._policy_api = None

    async def is_healthy(self) -> bool:
        if not self._core_api:
            return False
        try:
            await asyncio.to_thread(self._core_api.list_namespace, limit=1)
            return True
        except Exception:
            return False

    async def collect_pod_limits(
        self,
    ) -> dict:
        """Return {(namespace, pod_name): (cpu_limit_m, memory_limit_bytes)} for running pods."""
        if not self._core_api:
            return {}
        try:
            result = await asyncio.to_thread(
                self._core_api.list_pod_for_all_namespaces,
                field_selector="status.phase=Running",
            )
        except Exception as e:
            logger.error("k8s_api_collector.pod_limits_error", error=str(e))
            return {}

        limits: dict = {}
        for pod in result.items:
            ns = pod.metadata.namespace
            name = pod.metadata.name
            total_cpu: Optional[int] = None
            total_mem: Optional[int] = None
            for container in pod.spec.containers:
                container_limits = container.resources.limits
                if not container_limits:
                    continue
                if "cpu" in container_limits:
                    parsed = _parse_cpu_millicores(container_limits["cpu"])
                    total_cpu = (total_cpu or 0) + parsed
                if "memory" in container_limits:
                    parsed = _parse_memory_bytes(container_limits["memory"])
                    total_mem = (total_mem or 0) + parsed
            limits[(ns, name)] = (total_cpu, total_mem)
        return limits

    async def collect_events(self, namespace: str = "") -> List[KubernetesEvent]:
        if not self._core_api:
            return []
        try:
            if namespace:
                result = await asyncio.to_thread(
                    self._core_api.list_namespaced_event,
                    namespace,
                    field_selector="type=Warning",
                )
            else:
                result = await asyncio.to_thread(
                    self._core_api.list_event_for_all_namespaces,
                    field_selector="type=Warning",
                )
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

    async def collect_resource_states(self, namespace: str = "") -> List[ResourceState]:
        states: List[ResourceState] = []
        now = datetime.now(timezone.utc)

        states.extend(await self._collect_nodes(now))
        states.extend(await self._collect_services(namespace, now))
        states.extend(await self._collect_pdbs(namespace, now))
        states.extend(await self._collect_pvs(now))
        states.extend(await self._collect_namespaces(now))
        states.extend(await self._collect_deployments(namespace, now))
        states.extend(await self._collect_statefulsets(namespace, now))
        states.extend(await self._collect_daemonsets(namespace, now))
        states.extend(await self._collect_jobs(namespace, now))
        states.extend(await self._collect_cronjobs(namespace, now))
        states.extend(await self._collect_pvcs(namespace, now))
        states.extend(await self._collect_hpa(namespace, now))
        states.extend(await self._collect_networkpolicies(namespace, now))
        states.extend(await self._collect_quotas(namespace, now))
        states.extend(await self._collect_ingresses(namespace, now))

        return states

    async def _collect_nodes(self, now: datetime) -> List[ResourceState]:
        if not self._core_api:
            return []
        try:
            result = await asyncio.to_thread(self._core_api.list_node)
        except Exception as e:
            logger.error("k8s_api_collector.nodes_error", error=str(e))
            return []

        states = []
        for node in result.items:
            cond_map = {c.type: c.status for c in (node.status.conditions or [])}
            states.append(
                ResourceState(
                    kind="Node",
                    name=node.metadata.name,
                    namespace="",
                    conditions={
                        "ready": cond_map.get("Ready") == "True",
                        "memory_pressure": cond_map.get("MemoryPressure") == "True",
                        "disk_pressure": cond_map.get("DiskPressure") == "True",
                        "pid_pressure": cond_map.get("PIDPressure") == "True",
                        "unschedulable": bool(node.spec.unschedulable),
                    },
                    timestamp=now,
                )
            )
        return states

    async def _collect_services(
        self, namespace: str, now: datetime
    ) -> List[ResourceState]:
        if not self._core_api:
            return []
        try:
            if namespace:
                svc_result = await asyncio.to_thread(
                    self._core_api.list_namespaced_service, namespace
                )
                ep_result = await asyncio.to_thread(
                    self._core_api.list_namespaced_endpoints, namespace
                )
            else:
                svc_result = await asyncio.to_thread(
                    self._core_api.list_service_for_all_namespaces
                )
                ep_result = await asyncio.to_thread(
                    self._core_api.list_endpoints_for_all_namespaces
                )
        except Exception as e:
            logger.error("k8s_api_collector.services_error", error=str(e))
            return []

        ep_map = {
            (ep.metadata.namespace, ep.metadata.name): ep for ep in ep_result.items
        }

        states = []
        for svc in svc_result.items:
            ns = svc.metadata.namespace
            name = svc.metadata.name
            has_selector = bool(svc.spec.selector)
            if not has_selector:
                continue  # ExternalName, headless, or manually managed — skip
            ep = ep_map.get((ns, name))
            if ep and ep.subsets:
                ready = sum(len(s.addresses or []) for s in ep.subsets)
            else:
                ready = 0
            states.append(
                ResourceState(
                    kind="Service",
                    name=name,
                    namespace=ns,
                    ready_replicas=ready,
                    conditions={
                        "ready_endpoints": ready,
                        "service_type": svc.spec.type or "ClusterIP",
                        "cluster_ip": svc.spec.cluster_ip or "",
                    },
                    timestamp=now,
                )
            )
        return states

    async def _collect_pdbs(self, namespace: str, now: datetime) -> List[ResourceState]:
        if not self._policy_api:
            return []
        try:
            if namespace:
                result = await asyncio.to_thread(
                    self._policy_api.list_namespaced_pod_disruption_budget, namespace
                )
            else:
                result = await asyncio.to_thread(
                    self._policy_api.list_pod_disruption_budget_for_all_namespaces
                )
        except Exception as e:
            logger.error("k8s_api_collector.pdbs_error", error=str(e))
            return []

        return [
            ResourceState(
                kind="PodDisruptionBudget",
                name=pdb.metadata.name,
                namespace=pdb.metadata.namespace,
                conditions={
                    "current_healthy": pdb.status.current_healthy or 0,
                    "desired_healthy": pdb.status.desired_healthy or 0,
                    "disruptions_allowed": pdb.status.disruptions_allowed or 0,
                    "expected_pods": pdb.status.expected_pods or 0,
                },
                timestamp=now,
            )
            for pdb in result.items
        ]

    async def _collect_pvs(self, now: datetime) -> List[ResourceState]:
        if not self._core_api:
            return []
        try:
            result = await asyncio.to_thread(self._core_api.list_persistent_volume)
        except Exception as e:
            logger.error("k8s_api_collector.pvs_error", error=str(e))
            return []

        states = []
        for pv in result.items:
            claim_ref = ""
            if pv.spec.claim_ref:
                claim_ref = f"{pv.spec.claim_ref.namespace}/{pv.spec.claim_ref.name}"
            states.append(
                ResourceState(
                    kind="PersistentVolume",
                    name=pv.metadata.name,
                    namespace="",
                    conditions={
                        "phase": pv.status.phase or "Unknown",
                        "capacity": (pv.spec.capacity or {}).get("storage", ""),
                        "storage_class": pv.spec.storage_class_name or "",
                        "reclaim_policy": (
                            pv.spec.persistent_volume_reclaim_policy or ""
                        ),
                        "claim_ref": claim_ref,
                    },
                    timestamp=now,
                )
            )
        return states

    async def _collect_namespaces(self, now: datetime) -> List[ResourceState]:
        if not self._core_api:
            return []
        try:
            result = await asyncio.to_thread(self._core_api.list_namespace)
        except Exception as e:
            logger.error("k8s_api_collector.namespaces_error", error=str(e))
            return []

        return [
            ResourceState(
                kind="Namespace",
                name=ns.metadata.name,
                namespace="",
                conditions={"phase": ns.status.phase or "Unknown"},
                timestamp=now,
            )
            for ns in result.items
        ]

    async def _collect_deployments(
        self, namespace: str, now: datetime
    ) -> List[ResourceState]:
        if not self._apps_api:
            return []
        try:
            if namespace:
                result = await asyncio.to_thread(
                    self._apps_api.list_namespaced_deployment, namespace
                )
            else:
                result = await asyncio.to_thread(
                    self._apps_api.list_deployment_for_all_namespaces
                )
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
                result = await asyncio.to_thread(
                    self._apps_api.list_namespaced_stateful_set, namespace
                )
            else:
                result = await asyncio.to_thread(
                    self._apps_api.list_stateful_set_for_all_namespaces
                )
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
                result = await asyncio.to_thread(
                    self._apps_api.list_namespaced_daemon_set, namespace
                )
            else:
                result = await asyncio.to_thread(
                    self._apps_api.list_daemon_set_for_all_namespaces
                )
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

    async def _collect_jobs(self, namespace: str, now: datetime) -> List[ResourceState]:
        if not self._batch_api:
            return []
        try:
            if namespace:
                result = await asyncio.to_thread(
                    self._batch_api.list_namespaced_job, namespace
                )
            else:
                result = await asyncio.to_thread(
                    self._batch_api.list_job_for_all_namespaces
                )
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
                result = await asyncio.to_thread(
                    self._batch_api.list_namespaced_cron_job, namespace
                )
            else:
                result = await asyncio.to_thread(
                    self._batch_api.list_cron_job_for_all_namespaces
                )
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

    async def _collect_pvcs(self, namespace: str, now: datetime) -> List[ResourceState]:
        if not self._core_api:
            return []
        try:
            if namespace:
                result = await asyncio.to_thread(
                    self._core_api.list_namespaced_persistent_volume_claim, namespace
                )
            else:
                result = await asyncio.to_thread(
                    self._core_api.list_persistent_volume_claim_for_all_namespaces
                )
        except Exception as e:
            logger.error("k8s_api_collector.pvcs_error", error=str(e))
            return []

        return [
            ResourceState(
                kind="PersistentVolumeClaim",
                name=p.metadata.name,
                namespace=p.metadata.namespace,
                conditions={
                    "status": p.status.phase or "Unknown",
                    "capacity": (p.spec.resources.requests or {}).get("storage", ""),
                    "storage_class": p.spec.storage_class_name or "",
                },
                timestamp=now,
            )
            for p in result.items
        ]

    async def _collect_hpa(self, namespace: str, now: datetime) -> List[ResourceState]:
        if not self._autoscaling_api:
            return []
        try:
            if namespace:
                result = await asyncio.to_thread(
                    self._autoscaling_api.list_namespaced_horizontal_pod_autoscaler,
                    namespace,
                )
            else:
                result = await asyncio.to_thread(
                    self._autoscaling_api.list_horizontal_pod_autoscaler_for_all_namespaces
                )
        except Exception as e:
            logger.error("k8s_api_collector.hpa_error", error=str(e))
            return []

        return [
            ResourceState(
                kind="HorizontalPodAutoscaler",
                name=h.metadata.name,
                namespace=h.metadata.namespace,
                desired_replicas=h.spec.max_replicas,
                ready_replicas=h.status.current_replicas or 0,
                conditions={
                    "min_replicas": h.spec.min_replicas or 1,
                    "max_replicas": h.spec.max_replicas,
                    "target": f"{h.spec.scale_target_ref.kind}/{h.spec.scale_target_ref.name}",
                },
                timestamp=now,
            )
            for h in result.items
        ]

    async def _collect_networkpolicies(
        self, namespace: str, now: datetime
    ) -> List[ResourceState]:
        if not self._networking_api:
            return []
        try:
            if namespace:
                result = await asyncio.to_thread(
                    self._networking_api.list_namespaced_network_policy, namespace
                )
            else:
                result = await asyncio.to_thread(
                    self._networking_api.list_network_policy_for_all_namespaces
                )
        except Exception as e:
            logger.error("k8s_api_collector.networkpolicies_error", error=str(e))
            return []

        return [
            ResourceState(
                kind="NetworkPolicy",
                name=np.metadata.name,
                namespace=np.metadata.namespace,
                conditions={
                    "pod_selector": str(np.spec.pod_selector.match_labels or {}),
                },
                timestamp=now,
            )
            for np in result.items
        ]

    async def _collect_quotas(
        self, namespace: str, now: datetime
    ) -> List[ResourceState]:
        if not self._core_api:
            return []
        try:
            if namespace:
                result = await asyncio.to_thread(
                    self._core_api.list_namespaced_resource_quota, namespace
                )
            else:
                result = await asyncio.to_thread(
                    self._core_api.list_resource_quota_for_all_namespaces
                )
        except Exception as e:
            logger.error("k8s_api_collector.quotas_error", error=str(e))
            return []

        states = []
        for q in result.items:
            used = q.status.used or {}
            hard = q.status.hard or {}
            states.append(
                ResourceState(
                    kind="ResourceQuota",
                    name=q.metadata.name,
                    namespace=q.metadata.namespace,
                    conditions={
                        "cpu_used": used.get("cpu", ""),
                        "cpu_hard": hard.get("cpu", ""),
                        "memory_used": used.get("memory", ""),
                        "memory_hard": hard.get("memory", ""),
                    },
                    timestamp=now,
                )
            )
        return states

    async def _collect_ingresses(
        self, namespace: str, now: datetime
    ) -> List[ResourceState]:
        if not self._networking_api:
            return []
        try:
            if namespace:
                result = await asyncio.to_thread(
                    self._networking_api.list_namespaced_ingress, namespace
                )
            else:
                result = await asyncio.to_thread(
                    self._networking_api.list_ingress_for_all_namespaces
                )
        except Exception as e:
            logger.error("k8s_api_collector.ingresses_error", error=str(e))
            return []

        return [
            ResourceState(
                kind="Ingress",
                name=ing.metadata.name,
                namespace=ing.metadata.namespace,
                conditions={
                    "rules": len(ing.spec.rules or []),
                    "tls": bool(ing.spec.tls),
                },
                timestamp=now,
            )
            for ing in result.items
        ]
