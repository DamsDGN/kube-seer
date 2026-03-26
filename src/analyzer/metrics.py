import uuid
from datetime import datetime, timezone
from typing import List, Optional

import numpy as np
import structlog
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from src.analyzer.base import BaseAnalyzer
from src.config import Config
from src.models import Anomaly, NodeMetrics, PodMetrics, Severity

logger = structlog.get_logger()

UNHEALTHY_STATUSES = {"CrashLoopBackOff", "Error", "ImagePullBackOff", "OOMKilled"}
HIGH_RESTART_THRESHOLD = 5


class MetricsAnalyzer(BaseAnalyzer):
    def __init__(self, config: Config):
        self._config = config
        self._node_model: Optional[IsolationForest] = None
        self._node_scaler: Optional[StandardScaler] = None
        self._node_buffer: List[List[float]] = []
        self._node_samples_count = 0
        self._pod_model: Optional[IsolationForest] = None
        self._pod_scaler: Optional[StandardScaler] = None
        self._pod_buffer: List[List[float]] = []
        self._pod_samples_count = 0

    async def analyze(
        self, node_metrics: List[NodeMetrics], pod_metrics: List[PodMetrics]
    ) -> List[Anomaly]:
        anomalies: List[Anomaly] = []
        anomalies.extend(self._check_node_thresholds(node_metrics))
        anomalies.extend(self._check_pod_thresholds(pod_metrics))
        anomalies.extend(self._check_node_ml(node_metrics))
        anomalies.extend(self._check_pod_ml(pod_metrics))
        return anomalies

    async def update_model(
        self, node_metrics: List[NodeMetrics], pod_metrics: List[PodMetrics]
    ) -> None:
        for node in node_metrics:
            self._node_buffer.append(self._node_features(node))
            self._node_samples_count += 1
        for pod in pod_metrics:
            self._pod_buffer.append(self._pod_features(pod))
            self._pod_samples_count += 1
        min_samples = min(self._config.ml_window_size, 50)
        if len(self._node_buffer) >= min_samples:
            self._train_node_model()
        if len(self._pod_buffer) >= min_samples:
            self._train_pod_model()

    def _check_node_thresholds(self, nodes: List[NodeMetrics]) -> List[Anomaly]:
        anomalies = []
        for node in nodes:
            anomalies.extend(self._check_metric(
                value=node.cpu_usage_percent,
                warning=self._config.thresholds_cpu_warning,
                critical=self._config.thresholds_cpu_critical,
                metric_name="CPU",
                resource_type="node",
                resource_name=node.node_name,
                timestamp=node.timestamp,
            ))
            anomalies.extend(self._check_metric(
                value=node.memory_usage_percent,
                warning=self._config.thresholds_memory_warning,
                critical=self._config.thresholds_memory_critical,
                metric_name="Memory",
                resource_type="node",
                resource_name=node.node_name,
                timestamp=node.timestamp,
            ))
            anomalies.extend(self._check_metric(
                value=node.disk_usage_percent,
                warning=self._config.thresholds_disk_warning,
                critical=self._config.thresholds_disk_critical,
                metric_name="Disk",
                resource_type="node",
                resource_name=node.node_name,
                timestamp=node.timestamp,
            ))
        return anomalies

    def _check_pod_thresholds(self, pods: List[PodMetrics]) -> List[Anomaly]:
        anomalies = []
        for pod in pods:
            if pod.restart_count >= HIGH_RESTART_THRESHOLD:
                anomalies.append(Anomaly(
                    anomaly_id=str(uuid.uuid4()),
                    source="metrics",
                    severity=Severity.CRITICAL,
                    resource_type="pod",
                    resource_name=pod.pod_name,
                    namespace=pod.namespace,
                    description=f"High restart count: {pod.restart_count}",
                    score=min(pod.restart_count / 20.0, 1.0),
                    details={"restart_count": pod.restart_count, "status": pod.status},
                    timestamp=pod.timestamp,
                ))
            if pod.status in UNHEALTHY_STATUSES:
                anomalies.append(Anomaly(
                    anomaly_id=str(uuid.uuid4()),
                    source="metrics",
                    severity=Severity.CRITICAL,
                    resource_type="pod",
                    resource_name=pod.pod_name,
                    namespace=pod.namespace,
                    description=f"Unhealthy status: {pod.status}",
                    score=1.0,
                    details={"status": pod.status},
                    timestamp=pod.timestamp,
                ))
        return anomalies

    def _check_metric(
        self, value: float, warning: float, critical: float,
        metric_name: str, resource_type: str, resource_name: str,
        timestamp: datetime, namespace: str = "",
    ) -> List[Anomaly]:
        if value >= critical:
            return [Anomaly(
                anomaly_id=str(uuid.uuid4()),
                source="metrics",
                severity=Severity.CRITICAL,
                resource_type=resource_type,
                resource_name=resource_name,
                namespace=namespace,
                description=f"{metric_name} usage critical: {value:.1f}%",
                score=min(value / 100.0, 1.0),
                details={f"{metric_name.lower()}_usage_percent": value},
                timestamp=timestamp,
            )]
        if value >= warning:
            return [Anomaly(
                anomaly_id=str(uuid.uuid4()),
                source="metrics",
                severity=Severity.WARNING,
                resource_type=resource_type,
                resource_name=resource_name,
                namespace=namespace,
                description=f"{metric_name} usage warning: {value:.1f}%",
                score=value / 100.0,
                details={f"{metric_name.lower()}_usage_percent": value},
                timestamp=timestamp,
            )]
        return []

    def _node_features(self, node: NodeMetrics) -> List[float]:
        return [
            node.cpu_usage_percent, node.memory_usage_percent,
            node.disk_usage_percent, float(node.network_rx_bytes),
            float(node.network_tx_bytes),
        ]

    def _pod_features(self, pod: PodMetrics) -> List[float]:
        return [
            float(pod.cpu_usage_millicores),
            float(pod.memory_usage_bytes),
            float(pod.restart_count),
        ]

    def _train_node_model(self) -> None:
        data = np.array(self._node_buffer[-self._config.ml_window_size:])
        self._node_scaler = StandardScaler()
        scaled = self._node_scaler.fit_transform(data)
        self._node_model = IsolationForest(
            contamination=self._config.ml_anomaly_threshold,
            n_estimators=100, random_state=42,
        )
        self._node_model.fit(scaled)
        logger.info("metrics_analyzer.node_model_trained", samples=len(data))

    def _train_pod_model(self) -> None:
        data = np.array(self._pod_buffer[-self._config.ml_window_size:])
        self._pod_scaler = StandardScaler()
        scaled = self._pod_scaler.fit_transform(data)
        self._pod_model = IsolationForest(
            contamination=self._config.ml_anomaly_threshold,
            n_estimators=100, random_state=42,
        )
        self._pod_model.fit(scaled)
        logger.info("metrics_analyzer.pod_model_trained", samples=len(data))

    def _check_node_ml(self, nodes: List[NodeMetrics]) -> List[Anomaly]:
        if not self._node_model or not self._node_scaler or not nodes:
            return []
        anomalies = []
        features = np.array([self._node_features(n) for n in nodes])
        scaled = self._node_scaler.transform(features)
        predictions = self._node_model.predict(scaled)
        scores = self._node_model.decision_function(scaled)
        for i, node in enumerate(nodes):
            if predictions[i] == -1:
                anomalies.append(Anomaly(
                    anomaly_id=str(uuid.uuid4()),
                    source="metrics_ml",
                    severity=Severity.WARNING,
                    resource_type="node",
                    resource_name=node.node_name,
                    namespace="",
                    description=f"ML anomaly detected on node {node.node_name}",
                    score=max(0.0, min(1.0, -scores[i])),
                    details={"cpu": node.cpu_usage_percent, "memory": node.memory_usage_percent, "disk": node.disk_usage_percent},
                    timestamp=node.timestamp,
                ))
        return anomalies

    def _check_pod_ml(self, pods: List[PodMetrics]) -> List[Anomaly]:
        if not self._pod_model or not self._pod_scaler or not pods:
            return []
        anomalies = []
        features = np.array([self._pod_features(p) for p in pods])
        scaled = self._pod_scaler.transform(features)
        predictions = self._pod_model.predict(scaled)
        scores = self._pod_model.decision_function(scaled)
        for i, pod in enumerate(pods):
            if predictions[i] == -1:
                anomalies.append(Anomaly(
                    anomaly_id=str(uuid.uuid4()),
                    source="metrics_ml",
                    severity=Severity.WARNING,
                    resource_type="pod",
                    resource_name=pod.pod_name,
                    namespace=pod.namespace,
                    description=f"ML anomaly detected on pod {pod.pod_name}",
                    score=max(0.0, min(1.0, -scores[i])),
                    details={"cpu_millicores": pod.cpu_usage_millicores, "memory_bytes": pod.memory_usage_bytes, "restarts": pod.restart_count},
                    timestamp=pod.timestamp,
                ))
        return anomalies
