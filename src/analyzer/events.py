import uuid
from collections import Counter
from typing import Dict, List, Set

import structlog

from src.analyzer.base import BaseAnalyzer
from src.config import Config
from src.models import Anomaly, KubernetesEvent, Severity

logger = structlog.get_logger()

CRITICAL_REASONS: Dict[str, Severity] = {
    "OOMKilled": Severity.CRITICAL,
    "OOMKilling": Severity.CRITICAL,
    "CrashLoopBackOff": Severity.CRITICAL,
    "FailedMount": Severity.CRITICAL,
    "FailedAttachVolume": Severity.CRITICAL,
    "NodeNotReady": Severity.CRITICAL,
    "FailedScheduling": Severity.WARNING,
    "BackOff": Severity.WARNING,
    "Unhealthy": Severity.WARNING,
    "FailedCreate": Severity.WARNING,
    "FailedKillPod": Severity.WARNING,
    "Evicted": Severity.WARNING,
    "ImagePullBackOff": Severity.WARNING,
    "ErrImagePull": Severity.WARNING,
}

EVENT_BURST_THRESHOLD = 10


class EventAnalyzer(BaseAnalyzer):
    def __init__(self, config: Config):
        self._config = config

    async def analyze(self, events: List[KubernetesEvent]) -> List[Anomaly]:
        anomalies: List[Anomaly] = []
        anomalies.extend(self._check_patterns(events))
        anomalies.extend(self._check_frequency(events))
        return anomalies

    async def update_model(self, **kwargs) -> None:
        pass

    def _check_patterns(self, events: List[KubernetesEvent]) -> List[Anomaly]:
        anomalies = []
        seen: Set[str] = set()
        for event in events:
            if event.reason in CRITICAL_REASONS:
                key = f"{event.reason}:{event.involved_object_namespace}/{event.involved_object_name}"
                if key in seen:
                    continue
                seen.add(key)
                severity = CRITICAL_REASONS[event.reason]
                anomalies.append(Anomaly(
                    anomaly_id=str(uuid.uuid4()),
                    source="events",
                    severity=severity,
                    resource_type=event.involved_object_kind.lower(),
                    resource_name=event.involved_object_name,
                    namespace=event.involved_object_namespace,
                    description=f"{event.reason}: {event.message}",
                    score=1.0 if severity == Severity.CRITICAL else 0.7,
                    details={"reason": event.reason, "count": event.count, "event_type": event.event_type},
                    timestamp=event.last_timestamp,
                ))
        return anomalies

    def _check_frequency(self, events: List[KubernetesEvent]) -> List[Anomaly]:
        if not events:
            return []
        resource_counts: Counter = Counter()
        for event in events:
            if event.event_type == "Warning":
                key = f"{event.involved_object_namespace}/{event.involved_object_name}"
                resource_counts[key] += 1
        anomalies = []
        for resource_key, count in resource_counts.items():
            if count >= EVENT_BURST_THRESHOLD:
                namespace, name = resource_key.split("/", 1) if "/" in resource_key else ("", resource_key)
                anomalies.append(Anomaly(
                    anomaly_id=str(uuid.uuid4()),
                    source="events",
                    severity=Severity.WARNING,
                    resource_type="pod",
                    resource_name=name,
                    namespace=namespace,
                    description=f"Event burst: {count} warning events",
                    score=min(count / 30.0, 1.0),
                    details={"warning_event_count": count},
                    timestamp=events[-1].last_timestamp,
                ))
        return anomalies
