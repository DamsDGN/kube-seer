import re
import uuid
from typing import List

import structlog

from src.analyzer.base import BaseAnalyzer
from src.config import Config
from src.models import Anomaly, ResourceState, Severity

logger = structlog.get_logger()

# Minimum replicas below which degraded state is not reported (0 = scaled down intentionally)
_REPLICA_ZERO_SKIP = True

# ResourceQuota usage threshold to fire a warning
QUOTA_WARNING_PCT = 80.0


def _parse_quantity(value: str) -> float:
    """Convert a Kubernetes resource quantity string to a float.

    CPU  : "500m" → 0.5,  "2" → 2.0
    Memory: "256Mi" → 268435456.0,  "1Gi" → 1073741824.0
    """
    if not value:
        return 0.0
    value = value.strip()
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
        if value.endswith(suffix):
            return float(value[: -len(suffix)]) * multiplier
    if value.endswith("m"):
        return float(value[:-1]) / 1000
    try:
        return float(value)
    except ValueError:
        return 0.0


def _usage_pct(used: str, hard: str) -> float:
    h = _parse_quantity(hard)
    if h == 0:
        return 0.0
    return (_parse_quantity(used) / h) * 100


class ResourceStateAnalyzer(BaseAnalyzer):
    def __init__(self, config: Config):
        self._config = config

    async def analyze(  # type: ignore[override]
        self, resource_states: List[ResourceState]
    ) -> List[Anomaly]:
        anomalies: List[Anomaly] = []
        for rs in resource_states:
            kind = rs.kind
            if kind == "Node":
                anomalies.extend(self._check_node(rs))
            elif kind == "Service":
                anomalies.extend(self._check_service(rs))
            elif kind == "PodDisruptionBudget":
                anomalies.extend(self._check_pdb(rs))
            elif kind == "PersistentVolume":
                anomalies.extend(self._check_pv(rs))
            elif kind == "Namespace":
                anomalies.extend(self._check_namespace(rs))
            elif kind in ("Deployment", "StatefulSet", "DaemonSet"):
                anomalies.extend(self._check_replicas(rs))
            elif kind == "Job":
                anomalies.extend(self._check_job(rs))
            elif kind == "CronJob":
                anomalies.extend(self._check_cronjob(rs))
            elif kind == "PersistentVolumeClaim":
                anomalies.extend(self._check_pvc(rs))
            elif kind == "HorizontalPodAutoscaler":
                anomalies.extend(self._check_hpa(rs))
            elif kind == "ResourceQuota":
                anomalies.extend(self._check_quota(rs))
        return anomalies

    async def update_model(self, **kwargs) -> None:
        pass

    # ── Checks ────────────────────────────────────────────────────────────────

    def _check_node(self, rs: ResourceState) -> List[Anomaly]:
        anomalies = []
        c = rs.conditions
        if not c.get("ready", True):
            anomalies.append(
                self._anomaly(rs, Severity.CRITICAL, f"Node {rs.name} is NotReady")
            )
        if c.get("memory_pressure"):
            anomalies.append(
                self._anomaly(
                    rs, Severity.CRITICAL, f"Node {rs.name} has MemoryPressure"
                )
            )
        if c.get("disk_pressure"):
            anomalies.append(
                self._anomaly(rs, Severity.CRITICAL, f"Node {rs.name} has DiskPressure")
            )
        if c.get("pid_pressure"):
            anomalies.append(
                self._anomaly(rs, Severity.WARNING, f"Node {rs.name} has PIDPressure")
            )
        if c.get("unschedulable"):
            anomalies.append(
                self._anomaly(
                    rs, Severity.WARNING, f"Node {rs.name} is unschedulable (cordoned)"
                )
            )
        return anomalies

    def _check_service(self, rs: ResourceState) -> List[Anomaly]:
        if rs.conditions.get("ready_endpoints", -1) == 0:
            return [
                self._anomaly(
                    rs,
                    Severity.CRITICAL,
                    f"Service {rs.namespace}/{rs.name} has a selector"
                    " but 0 ready endpoints (silent outage)",
                )
            ]
        return []

    def _check_pdb(self, rs: ResourceState) -> List[Anomaly]:
        current = rs.conditions.get("current_healthy", 0)
        desired = rs.conditions.get("desired_healthy", 0)
        if desired == 0:
            return []
        if current < desired:
            allowed = rs.conditions.get("disruptions_allowed", 0)
            return [
                self._anomaly(
                    rs,
                    Severity.CRITICAL,
                    f"PodDisruptionBudget {rs.namespace}/{rs.name} is violated:"
                    f" {current}/{desired} healthy pods"
                    f" (disruptions_allowed={allowed})",
                )
            ]
        return []

    def _check_pv(self, rs: ResourceState) -> List[Anomaly]:
        phase = rs.conditions.get("phase", "Unknown")
        if phase == "Failed":
            claim = rs.conditions.get("claim_ref", "none")
            return [
                self._anomaly(
                    rs,
                    Severity.CRITICAL,
                    f"PersistentVolume {rs.name} is in Failed phase (claim: {claim})",
                )
            ]
        if phase == "Released":
            capacity = rs.conditions.get("capacity", "?")
            policy = rs.conditions.get("reclaim_policy", "?")
            return [
                self._anomaly(
                    rs,
                    Severity.WARNING,
                    f"PersistentVolume {rs.name} is Released and not reclaimed"
                    f" (capacity: {capacity}, policy: {policy})",
                )
            ]
        return []

    def _check_namespace(self, rs: ResourceState) -> List[Anomaly]:
        if rs.conditions.get("phase") == "Terminating":
            return [
                self._anomaly(
                    rs,
                    Severity.CRITICAL,
                    f"Namespace {rs.name} is stuck in Terminating phase"
                    " (likely blocked by finalizers)",
                )
            ]
        return []

    def _check_replicas(self, rs: ResourceState) -> List[Anomaly]:
        desired = rs.desired_replicas
        ready = rs.ready_replicas if rs.ready_replicas is not None else 0
        if desired is None or desired == 0:
            return []
        if ready == 0:
            return [
                self._anomaly(
                    rs,
                    Severity.CRITICAL,
                    f"{rs.kind} {rs.namespace}/{rs.name} has 0/{desired} replicas ready",
                )
            ]
        if ready < desired:
            return [
                self._anomaly(
                    rs,
                    Severity.WARNING,
                    f"{rs.kind} {rs.namespace}/{rs.name} is degraded:"
                    f" {ready}/{desired} replicas ready",
                )
            ]
        return []

    def _check_job(self, rs: ResourceState) -> List[Anomaly]:
        desired = rs.desired_replicas
        succeeded = rs.ready_replicas if rs.ready_replicas is not None else 0
        if desired is None:
            return []
        if succeeded == 0:
            return [
                self._anomaly(
                    rs,
                    Severity.WARNING,
                    f"Job {rs.namespace}/{rs.name} has no successful completions (0/{desired})",
                )
            ]
        return []

    def _check_cronjob(self, rs: ResourceState) -> List[Anomaly]:
        if rs.conditions.get("suspended"):
            schedule = rs.conditions.get("schedule", "?")
            return [
                self._anomaly(
                    rs,
                    Severity.WARNING,
                    f"CronJob {rs.namespace}/{rs.name} is suspended (schedule: {schedule})",
                )
            ]
        return []

    def _check_pvc(self, rs: ResourceState) -> List[Anomaly]:
        status = rs.conditions.get("status", "Unknown")
        if status == "Bound":
            return []
        severity = Severity.CRITICAL if status == "Lost" else Severity.WARNING
        capacity = rs.conditions.get("capacity", "")
        storage_class = rs.conditions.get("storage_class", "")
        extra = ""
        if capacity:
            extra = (
                f" ({capacity}, {storage_class})" if storage_class else f" ({capacity})"
            )
        return [
            self._anomaly(
                rs,
                severity,
                f"PersistentVolumeClaim {rs.namespace}/{rs.name} is {status}{extra}",
            )
        ]

    def _check_hpa(self, rs: ResourceState) -> List[Anomaly]:
        current = rs.ready_replicas if rs.ready_replicas is not None else 0
        max_replicas = rs.conditions.get("max_replicas")
        target = rs.conditions.get("target", "")
        if max_replicas and current >= max_replicas:
            return [
                self._anomaly(
                    rs,
                    Severity.WARNING,
                    f"HorizontalPodAutoscaler {rs.namespace}/{rs.name} is at max replicas"
                    f" ({current}/{max_replicas}) for {target} — cannot scale further",
                )
            ]
        return []

    def _check_quota(self, rs: ResourceState) -> List[Anomaly]:
        anomalies = []
        cpu_pct = _usage_pct(
            rs.conditions.get("cpu_used", ""),
            rs.conditions.get("cpu_hard", ""),
        )
        mem_pct = _usage_pct(
            rs.conditions.get("memory_used", ""),
            rs.conditions.get("memory_hard", ""),
        )
        if cpu_pct >= QUOTA_WARNING_PCT:
            anomalies.append(
                self._anomaly(
                    rs,
                    Severity.WARNING,
                    f"ResourceQuota {rs.namespace}/{rs.name}: CPU at {cpu_pct:.0f}%"
                    f" ({rs.conditions.get('cpu_used')}/{rs.conditions.get('cpu_hard')})",
                )
            )
        if mem_pct >= QUOTA_WARNING_PCT:
            anomalies.append(
                self._anomaly(
                    rs,
                    Severity.WARNING,
                    f"ResourceQuota {rs.namespace}/{rs.name}: memory at {mem_pct:.0f}%"
                    f" ({rs.conditions.get('memory_used')}/{rs.conditions.get('memory_hard')})",
                )
            )
        return anomalies

    # ── Helper ────────────────────────────────────────────────────────────────

    def _anomaly(
        self, rs: ResourceState, severity: Severity, description: str
    ) -> Anomaly:
        return Anomaly(
            anomaly_id=str(uuid.uuid4()),
            source="resources",
            severity=severity,
            resource_type=re.sub(r"(?<!^)(?=[A-Z])", "_", rs.kind).lower(),
            resource_name=rs.name,
            namespace=rs.namespace,
            description=description,
            score=1.0 if severity == Severity.CRITICAL else 0.7,
            details=rs.conditions,
            timestamp=rs.timestamp,
        )
