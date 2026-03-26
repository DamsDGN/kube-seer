"""
Modèles de données pour l'agent SRE
"""

from datetime import datetime
from enum import IntEnum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class Severity(IntEnum):
    INFO = 0
    WARNING = 1
    CRITICAL = 2


class NodeMetrics(BaseModel):
    node_name: str
    cpu_usage_percent: float
    memory_usage_percent: float
    disk_usage_percent: float
    network_rx_bytes: int
    network_tx_bytes: int
    conditions: Dict[str, bool]
    timestamp: datetime


class PodMetrics(BaseModel):
    pod_name: str
    namespace: str
    node_name: str
    cpu_usage_millicores: int
    memory_usage_bytes: int
    restart_count: int
    status: str
    timestamp: datetime


class KubernetesEvent(BaseModel):
    event_type: str
    reason: str
    message: str
    involved_object_kind: str
    involved_object_name: str
    involved_object_namespace: str
    count: int
    first_timestamp: datetime
    last_timestamp: datetime


class ResourceState(BaseModel):
    kind: str
    name: str
    namespace: str
    desired_replicas: Optional[int] = None
    ready_replicas: Optional[int] = None
    conditions: Dict[str, Any] = {}
    timestamp: datetime


class CollectedData(BaseModel):
    node_metrics: List[NodeMetrics]
    pod_metrics: List[PodMetrics]
    events: List[KubernetesEvent]
    resource_states: List[ResourceState]
    collection_timestamp: datetime


class StoredRecord(BaseModel):
    record_type: str
    data: Dict[str, Any]
    timestamp: datetime
    cluster_name: str = ""


class Anomaly(BaseModel):
    anomaly_id: str
    source: str
    severity: Severity
    resource_type: str
    resource_name: str
    namespace: str = ""
    description: str
    score: float
    details: Dict[str, Any] = {}
    timestamp: datetime


class AnalysisResult(BaseModel):
    anomalies: List[Anomaly]
    incidents: List["Incident"] = []
    analysis_timestamp: datetime
    metrics_analyzed: int = 0
    logs_analyzed: int = 0
    events_analyzed: int = 0


class Incident(BaseModel):
    incident_id: str
    anomalies: List[Anomaly]
    severity: Severity
    score: float
    description: str
    resources: List[str]
    timestamp: datetime


AnalysisResult.model_rebuild()
