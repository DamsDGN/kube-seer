import uuid
from typing import Dict, List, Set

import structlog

from src.config import Config
from src.models import Anomaly, CollectedData, Incident, Severity

logger = structlog.get_logger()

TEMPORAL_WINDOW_SECONDS = 300


class Correlator:
    def __init__(self, config: Config):
        self._config = config

    async def correlate(
        self, anomalies: List[Anomaly], data: CollectedData
    ) -> List[Incident]:
        if not anomalies:
            return []
        pod_to_node = self._build_pod_node_map(data)
        groups = self._group_anomalies(anomalies, pod_to_node)
        incidents = self._build_incidents(groups)
        logger.info(
            "correlator.done", anomalies=len(anomalies), incidents=len(incidents),
        )
        return incidents

    def _build_pod_node_map(self, data: CollectedData) -> Dict[str, str]:
        pod_to_node: Dict[str, str] = {}
        for pod in data.pod_metrics:
            if pod.node_name:
                key = f"{pod.namespace}/{pod.pod_name}"
                pod_to_node[key] = pod.node_name
        return pod_to_node

    def _resource_key(self, anomaly: Anomaly) -> str:
        if anomaly.namespace:
            return f"{anomaly.namespace}/{anomaly.resource_type}/{anomaly.resource_name}"
        return f"{anomaly.resource_type}/{anomaly.resource_name}"

    def _get_node_for_anomaly(
        self, anomaly: Anomaly, pod_to_node: Dict[str, str]
    ) -> str:
        if anomaly.resource_type == "node":
            return anomaly.resource_name
        if anomaly.resource_type == "pod":
            pod_key = f"{anomaly.namespace}/{anomaly.resource_name}"
            return pod_to_node.get(pod_key, "")
        return ""

    def _group_anomalies(
        self, anomalies: List[Anomaly], pod_to_node: Dict[str, str],
    ) -> List[List[Anomaly]]:
        n = len(anomalies)
        related: Dict[int, Set[int]] = {i: set() for i in range(n)}
        for i in range(n):
            for j in range(i + 1, n):
                if self._are_related(anomalies[i], anomalies[j], pod_to_node):
                    related[i].add(j)
                    related[j].add(i)
        visited: Set[int] = set()
        groups: List[List[Anomaly]] = []
        for i in range(n):
            if i in visited:
                continue
            group_indices: List[int] = []
            stack = [i]
            while stack:
                idx = stack.pop()
                if idx in visited:
                    continue
                visited.add(idx)
                group_indices.append(idx)
                stack.extend(related[idx] - visited)
            groups.append([anomalies[idx] for idx in group_indices])
        return groups

    def _are_related(
        self, a: Anomaly, b: Anomaly, pod_to_node: Dict[str, str],
    ) -> bool:
        time_diff = abs((a.timestamp - b.timestamp).total_seconds())
        if time_diff > TEMPORAL_WINDOW_SECONDS:
            return False
        if self._resource_key(a) == self._resource_key(b):
            return True
        node_a = self._get_node_for_anomaly(a, pod_to_node)
        node_b = self._get_node_for_anomaly(b, pod_to_node)
        if node_a and node_b and node_a == node_b:
            return True
        return False

    def _build_incidents(self, groups: List[List[Anomaly]]) -> List[Incident]:
        incidents = []
        for group in groups:
            max_severity = max(a.severity for a in group)
            max_score = max(a.score for a in group)
            resources = list({self._resource_key(a) for a in group})
            descriptions = [a.description for a in group]
            if len(group) == 1:
                desc = descriptions[0]
            else:
                desc = "Correlated: " + " + ".join(d[:50] for d in descriptions[:3])
                if len(descriptions) > 3:
                    desc += f" (+{len(descriptions) - 3} more)"
            earliest = min(a.timestamp for a in group)
            incidents.append(
                Incident(
                    incident_id=str(uuid.uuid4()),
                    anomalies=group,
                    severity=Severity(max_severity),
                    score=max_score,
                    description=desc,
                    resources=resources,
                    timestamp=earliest,
                )
            )
        return incidents
