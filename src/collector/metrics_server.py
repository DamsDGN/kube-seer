import asyncio
import structlog
from datetime import datetime, timezone
from typing import List, Optional

from kubernetes import client, config

from src.collector.base import MetricsCollector
from src.config import Config
from src.models import NodeMetrics, PodMetrics

logger = structlog.get_logger()


def _parse_cpu(cpu_str: str) -> int:
    """Parse CPU string to millicores. E.g. '500m' -> 500, '1' -> 1000."""
    if cpu_str.endswith("m"):
        return int(cpu_str[:-1])
    if cpu_str.endswith("n"):
        return int(cpu_str[:-1]) // 1_000_000
    return int(float(cpu_str) * 1000)


def _parse_memory(mem_str: str) -> int:
    """Parse memory string to bytes. E.g. '128Mi' -> 134217728."""
    suffixes = {
        "Ki": 1024,
        "Mi": 1024**2,
        "Gi": 1024**3,
        "Ti": 1024**4,
        "K": 1000,
        "M": 1000**2,
        "G": 1000**3,
        "T": 1000**4,
    }
    for suffix, multiplier in suffixes.items():
        if mem_str.endswith(suffix):
            return int(float(mem_str[: -len(suffix)]) * multiplier)
    return int(mem_str)


class MetricsServerCollector(MetricsCollector):
    def __init__(self, config_obj: Config):
        self._config = config_obj
        self._api: Optional[client.CustomObjectsApi] = None

    async def connect(self) -> None:
        try:
            config.load_incluster_config()
        except Exception:
            config.load_kube_config()
        self._api = client.CustomObjectsApi()
        logger.info("metrics_server_collector.connected")

    async def close(self) -> None:
        self._api = None

    async def is_healthy(self) -> bool:
        if not self._api:
            return False
        try:
            await asyncio.to_thread(
                self._api.list_cluster_custom_object,
                group="metrics.k8s.io",
                version="v1beta1",
                plural="nodes",
            )
            return True
        except Exception:
            return False

    async def collect_node_metrics(self) -> List[NodeMetrics]:
        if not self._api:
            return []
        try:
            result = await asyncio.to_thread(
                self._api.list_cluster_custom_object,
                group="metrics.k8s.io",
                version="v1beta1",
                plural="nodes",
            )
        except Exception as e:
            logger.error("metrics_server_collector.node_error", error=str(e))
            return []

        now = datetime.now(timezone.utc)
        nodes = []
        for item in result.get("items", []):
            nodes.append(
                NodeMetrics(
                    node_name=item["metadata"]["name"],
                    # metrics-server provides raw usage only, not percentages.
                    # Percentage calculation requires node capacity (available from Prometheus).
                    cpu_usage_percent=0.0,
                    memory_usage_percent=0.0,
                    disk_usage_percent=0.0,
                    network_rx_bytes=0,
                    network_tx_bytes=0,
                    conditions={},
                    timestamp=now,
                )
            )
        return nodes

    async def collect_pod_metrics(self, namespace: str = "") -> List[PodMetrics]:
        if not self._api:
            return []
        try:
            if namespace:
                result = await asyncio.to_thread(
                    self._api.list_namespaced_custom_object,
                    group="metrics.k8s.io",
                    version="v1beta1",
                    namespace=namespace,
                    plural="pods",
                )
            else:
                result = await asyncio.to_thread(
                    self._api.list_cluster_custom_object,
                    group="metrics.k8s.io",
                    version="v1beta1",
                    plural="pods",
                )
        except Exception as e:
            logger.error("metrics_server_collector.pod_error", error=str(e))
            return []

        now = datetime.now(timezone.utc)
        pods = []
        for item in result.get("items", []):
            containers = item.get("containers", [])
            total_cpu = sum(_parse_cpu(c["usage"].get("cpu", "0")) for c in containers)
            total_mem = sum(
                _parse_memory(c["usage"].get("memory", "0")) for c in containers
            )
            pods.append(
                PodMetrics(
                    pod_name=item["metadata"]["name"],
                    namespace=item["metadata"].get("namespace", ""),
                    node_name="",
                    cpu_usage_millicores=total_cpu,
                    memory_usage_bytes=total_mem,
                    restart_count=0,
                    status="Running",
                    timestamp=now,
                )
            )
        return pods
