from abc import ABC, abstractmethod
from typing import List

from src.models import Anomaly


class BaseAlerter(ABC):
    @abstractmethod
    async def send(self, anomalies: List[Anomaly]) -> int:
        """Send alerts for anomalies. Returns count of successfully sent alerts."""

    @abstractmethod
    async def is_healthy(self) -> bool:
        """Check if the alerting backend is reachable."""
