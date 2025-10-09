"""
Modèles de données pour l'agent SRE
"""

from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Dict, Any, Optional
from enum import Enum


class AlertSeverity(Enum):
    """Niveaux de sévérité des alertes"""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertType(Enum):
    """Types d'alertes"""

    CPU_ANOMALY = "cpu_anomaly"
    MEMORY_ANOMALY = "memory_anomaly"
    LOG_ERROR = "log_error"
    CORRELATED_ISSUE = "correlated_issue"
    SYSTEM_ERROR = "system_error"


@dataclass
class Metric:
    """Représente une métrique collectée"""

    pod_name: str
    cpu_usage: float
    memory_usage: float
    cpu_peak: float
    memory_peak: float
    timestamp: datetime
    namespace: str = ""
    node_name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire"""
        return {
            "pod_name": self.pod_name,
            "cpu_usage": self.cpu_usage,
            "memory_usage": self.memory_usage,
            "cpu_peak": self.cpu_peak,
            "memory_peak": self.memory_peak,
            "timestamp": self.timestamp.isoformat(),
            "namespace": self.namespace,
            "node_name": self.node_name,
        }


@dataclass
class LogEntry:
    """Représente une entrée de log"""

    pod_name: str
    namespace: str
    log_level: str
    message: str
    timestamp: datetime
    service: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire"""
        return {
            "pod_name": self.pod_name,
            "namespace": self.namespace,
            "log_level": self.log_level,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "service": self.service,
        }


@dataclass
class Alert:
    """Représente une alerte générée"""

    type: str
    severity: str
    message: str
    timestamp: datetime
    metadata: Dict[str, Any] = None
    resolved: bool = False

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire"""
        return {
            "type": self.type,
            "severity": self.severity,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "resolved": self.resolved,
        }


@dataclass
class AnomalyResult:
    """Résultat de détection d'anomalie"""

    is_anomaly: bool
    anomaly_score: float
    threshold: float
    features: Dict[str, float]
    timestamp: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire"""
        return {
            "is_anomaly": self.is_anomaly,
            "anomaly_score": self.anomaly_score,
            "threshold": self.threshold,
            "features": self.features,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ModelMetrics:
    """Métriques du modèle ML"""

    accuracy: float
    precision: float
    recall: float
    f1_score: float
    training_samples: int
    last_updated: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire"""
        return {
            "accuracy": self.accuracy,
            "precision": self.precision,
            "recall": self.recall,
            "f1_score": self.f1_score,
            "training_samples": self.training_samples,
            "last_updated": self.last_updated.isoformat(),
        }


@dataclass
class SystemHealth:
    """État de santé du système"""

    elasticsearch_status: str
    kubernetes_status: str
    agent_uptime: float
    alerts_count_24h: int
    last_analysis: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire"""
        return {
            "elasticsearch_status": self.elasticsearch_status,
            "kubernetes_status": self.kubernetes_status,
            "agent_uptime": self.agent_uptime,
            "alerts_count_24h": self.alerts_count_24h,
            "last_analysis": self.last_analysis.isoformat(),
        }
