import uuid
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Tuple

import numpy as np
import structlog

from src.config import Config
from src.models import NodeMetrics, PodMetrics, Prediction

logger = structlog.get_logger()

MIN_SAMPLES_FOR_PREDICTION = 5


class Predictor:
    def __init__(self, config: Config):
        self._config = config
        # resource_key -> metric_name -> list of (timestamp_hours, value)
        self._history: Dict[str, Dict[str, List[Tuple[float, float]]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self._max_history = config.ml_window_size

    async def update(
        self, node_metrics: List[NodeMetrics], pod_metrics: List[PodMetrics]
    ) -> None:
        for node in node_metrics:
            key = f"node/{node.node_name}"
            ts_h = node.timestamp.timestamp() / 3600.0
            self._append(key, "cpu_usage_percent", ts_h, node.cpu_usage_percent)
            self._append(key, "memory_usage_percent", ts_h, node.memory_usage_percent)
            self._append(key, "disk_usage_percent", ts_h, node.disk_usage_percent)

        for pod in pod_metrics:
            key = f"{pod.namespace}/pod/{pod.pod_name}"
            ts_h = pod.timestamp.timestamp() / 3600.0
            if pod.cpu_limit_millicores:
                cpu_pct = pod.cpu_usage_millicores / pod.cpu_limit_millicores * 100.0
                self._append(key, "cpu_pct", ts_h, cpu_pct)
            if pod.memory_limit_bytes:
                mem_pct = pod.memory_usage_bytes / pod.memory_limit_bytes * 100.0
                self._append(key, "memory_pct", ts_h, mem_pct)

    async def predict(
        self, node_metrics: List[NodeMetrics], pod_metrics: List[PodMetrics]
    ) -> tuple:
        predictions: List[Prediction] = []

        thresholds = {
            "cpu_usage_percent": self._config.thresholds_cpu_critical,
            "memory_usage_percent": self._config.thresholds_memory_critical,
            "disk_usage_percent": self._config.thresholds_disk_critical,
        }

        for node in node_metrics:
            key = f"node/{node.node_name}"
            for metric_name, threshold in thresholds.items():
                current = getattr(node, metric_name)
                pred = self._predict_metric(
                    key=key,
                    metric_name=metric_name,
                    current_value=current,
                    threshold=threshold,
                    resource_type="node",
                    resource_name=node.node_name,
                    namespace="",
                    timestamp=node.timestamp,
                )
                if pred:
                    predictions.append(pred)

        return predictions, []

    def _append(self, key: str, metric: str, ts_h: float, value: float) -> None:
        buf = self._history[key][metric]
        buf.append((ts_h, value))
        if len(buf) > self._max_history:
            self._history[key][metric] = buf[-self._max_history :]

    def _predict_metric(
        self,
        key: str,
        metric_name: str,
        current_value: float,
        threshold: float,
        resource_type: str,
        resource_name: str,
        namespace: str,
        timestamp: datetime,
    ) -> Prediction | None:
        buf = self._history.get(key, {}).get(metric_name, [])
        if len(buf) < MIN_SAMPLES_FOR_PREDICTION:
            return None

        times = np.array([t for t, _ in buf])
        values = np.array([v for _, v in buf])

        # Normalize times to start at 0
        t0 = times[0]
        times_norm = times - t0

        # Linear regression
        slope, intercept, r_squared = self._linear_regression(times_norm, values)

        # Only predict if trend is positive and meaningful
        if slope <= 0:
            return None

        # Already above threshold
        if current_value >= threshold:
            return None

        # Time to threshold from now
        current_t = times_norm[-1]
        threshold_t = (threshold - intercept) / slope
        hours_to_threshold = threshold_t - current_t

        if (
            hours_to_threshold <= 0
            or hours_to_threshold > self._config.prediction_horizon_hours
        ):
            return None

        predicted_value = min(
            intercept + slope * (current_t + hours_to_threshold), 100.0
        )

        return Prediction(
            prediction_id=str(uuid.uuid4()),
            resource_type=resource_type,
            resource_name=resource_name,
            namespace=namespace,
            metric_name=metric_name,
            current_value=current_value,
            predicted_value=predicted_value,
            threshold=threshold,
            hours_to_threshold=round(hours_to_threshold, 1),
            confidence=round(max(0.0, min(1.0, r_squared)), 2),
            trend_per_hour=round(slope, 4),
            description=(
                f"{metric_name} on {resource_type}/{resource_name}: "
                f"estimated to reach {threshold}% in {hours_to_threshold:.0f}h "
                f"(current: {current_value:.1f}%, trend: +{slope:.2f}%/h)"
            ),
            timestamp=timestamp,
        )

    def _linear_regression(
        self, x: np.ndarray, y: np.ndarray
    ) -> Tuple[float, float, float]:
        n = len(x)
        sum_x = np.sum(x)
        sum_y = np.sum(y)
        sum_xy = np.sum(x * y)
        sum_x2 = np.sum(x * x)

        denom = n * sum_x2 - sum_x * sum_x
        if abs(denom) < 1e-10:
            return 0.0, float(np.mean(y)), 0.0

        slope = float((n * sum_xy - sum_x * sum_y) / denom)
        intercept = float((sum_y - slope * sum_x) / n)

        # R-squared
        y_pred = slope * x + intercept
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

        return slope, intercept, r_squared
