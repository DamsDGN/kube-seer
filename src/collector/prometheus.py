import structlog
import httpx
from datetime import datetime, timezone
from typing import Dict, List, Optional

from src.collector.base import MetricsCollector
from src.config import Config
from src.models import NodeMetrics, PodMetrics

logger = structlog.get_logger()

# PromQL queries
NODE_CPU_QUERY = (
    '100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)'
)
NODE_MEMORY_QUERY = (
    "(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100"
)
NODE_DISK_QUERY = (
    '(1 - (node_filesystem_avail_bytes{mountpoint="/"}'
    ' / node_filesystem_size_bytes{mountpoint="/"})) * 100'
)
NODE_NETWORK_RX_QUERY = "rate(node_network_receive_bytes_total[5m])"
NODE_NETWORK_TX_QUERY = "rate(node_network_transmit_bytes_total[5m])"

POD_CPU_QUERY = (
    "sum by (pod, namespace, node) (rate(container_cpu_usage_seconds_total[5m])) * 1000"
)
POD_MEMORY_QUERY = "sum by (pod, namespace, node) (container_memory_working_set_bytes)"
POD_RESTART_QUERY = "sum by (pod, namespace) (kube_pod_container_status_restarts_total)"


class PrometheusCollector(MetricsCollector):
    def __init__(self, config: Config):
        self._config = config
        self._client: Optional[httpx.AsyncClient] = None
        self._base_url = config.collectors_prometheus_url

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=30.0)
        logger.info("prometheus_collector.connected", url=self._base_url)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def is_healthy(self) -> bool:
        if not self._client:
            return False
        try:
            resp = await self._client.get("/-/healthy")
            return resp.status_code == 200
        except Exception:
            return False

    async def _query(self, promql: str) -> List[Dict]:
        if not self._client:
            return []
        try:
            resp = await self._client.get("/api/v1/query", params={"query": promql})
            if resp.status_code != 200:
                logger.warning(
                    "prometheus_collector.query_failed",
                    query=promql,
                    status=resp.status_code,
                )
                return []
            data = resp.json()
            if data.get("status") != "success":
                return []
            return data.get("data", {}).get("result", [])
        except Exception as e:
            logger.error("prometheus_collector.query_error", query=promql, error=str(e))
            return []

    async def collect_node_metrics(self) -> List[NodeMetrics]:
        cpu_results = await self._query(NODE_CPU_QUERY)
        memory_results = await self._query(NODE_MEMORY_QUERY)
        disk_results = await self._query(NODE_DISK_QUERY)
        rx_results = await self._query(NODE_NETWORK_RX_QUERY)
        tx_results = await self._query(NODE_NETWORK_TX_QUERY)

        def _strip_port(instance: str) -> str:
            # Strip port from instance label (e.g. "192.168.1.5:9100" -> "192.168.1.5").
            # NOTE: This still won't match K8s node names (e.g. "node-1") from metrics-server.
            # Full dedup would require resolving node IPs to K8s node names.
            return instance.rsplit(":", 1)[0] if ":" in instance else instance

        def _by_instance(results: List[Dict]) -> Dict[str, float]:
            return {
                _strip_port(r["metric"].get("instance", "")): float(r["value"][1])
                for r in results
                if r.get("value")
            }

        cpu_map = _by_instance(cpu_results)
        mem_map = _by_instance(memory_results)
        disk_map = _by_instance(disk_results)
        rx_map = _by_instance(rx_results)
        tx_map = _by_instance(tx_results)

        now = datetime.now(timezone.utc)
        nodes = []
        for instance in cpu_map:
            nodes.append(
                NodeMetrics(
                    node_name=instance,
                    cpu_usage_percent=cpu_map.get(instance, 0.0),
                    memory_usage_percent=mem_map.get(instance, 0.0),
                    disk_usage_percent=disk_map.get(instance, 0.0),
                    network_rx_bytes=int(rx_map.get(instance, 0)),
                    network_tx_bytes=int(tx_map.get(instance, 0)),
                    conditions={},
                    timestamp=now,
                )
            )
        return nodes

    async def collect_pod_metrics(self, namespace: str = "") -> List[PodMetrics]:
        ns_filter = f'namespace="{namespace}"' if namespace else ""

        cpu_query = POD_CPU_QUERY
        mem_query = POD_MEMORY_QUERY
        restart_query = POD_RESTART_QUERY
        if ns_filter:
            cpu_query = (
                f"sum by (pod, namespace, node)"
                f" (rate(container_cpu_usage_seconds_total{{{ns_filter}}}[5m])) * 1000"
            )
            mem_query = (
                f"sum by (pod, namespace, node)"
                f" (container_memory_working_set_bytes{{{ns_filter}}})"
            )
            restart_query = (
                f"sum by (pod, namespace)"
                f" (kube_pod_container_status_restarts_total{{{ns_filter}}})"
            )

        cpu_results = await self._query(cpu_query)
        mem_results = await self._query(mem_query)
        restart_results = await self._query(restart_query)

        def _pod_key(metric: Dict) -> str:
            return f"{metric.get('namespace', '')}/{metric.get('pod', '')}"

        cpu_map = {
            _pod_key(r["metric"]): float(r["value"][1])
            for r in cpu_results
            if r.get("value")
        }
        mem_map = {
            _pod_key(r["metric"]): int(float(r["value"][1]))
            for r in mem_results
            if r.get("value")
        }
        restart_map = {
            _pod_key(r["metric"]): int(float(r["value"][1]))
            for r in restart_results
            if r.get("value")
        }

        now = datetime.now(timezone.utc)
        pods = []
        for r in cpu_results:
            metric = r["metric"]
            key = _pod_key(metric)
            pod_name = metric.get("pod", "")
            if not pod_name:
                continue
            pods.append(
                PodMetrics(
                    pod_name=pod_name,
                    namespace=metric.get("namespace", ""),
                    node_name=metric.get("node", ""),
                    cpu_usage_millicores=int(cpu_map.get(key, 0)),
                    memory_usage_bytes=mem_map.get(key, 0),
                    restart_count=restart_map.get(key, 0),
                    status="Running",
                    timestamp=now,
                )
            )
        return pods
