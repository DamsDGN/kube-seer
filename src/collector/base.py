from abc import ABC, abstractmethod
from typing import List

from src.models import (
    KubernetesEvent,
    NodeMetrics,
    PodMetrics,
    ResourceState,
)


class BaseCollector(ABC):
    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the data source."""

    @abstractmethod
    async def close(self) -> None:
        """Close connection to the data source."""

    @abstractmethod
    async def is_healthy(self) -> bool:
        """Check if the data source is reachable."""


class MetricsCollector(BaseCollector):
    @abstractmethod
    async def collect_node_metrics(self) -> List[NodeMetrics]:
        """Collect metrics for all nodes."""

    @abstractmethod
    async def collect_pod_metrics(self, namespace: str = "") -> List[PodMetrics]:
        """Collect metrics for pods. If namespace is empty, collect from all namespaces."""


class StateCollector(BaseCollector):
    @abstractmethod
    async def collect_events(self, namespace: str = "") -> List[KubernetesEvent]:
        """Collect Kubernetes events."""

    @abstractmethod
    async def collect_resource_states(self, namespace: str = "") -> List[ResourceState]:
        """Collect state of deployments, statefulsets, daemonsets, jobs, etc."""
