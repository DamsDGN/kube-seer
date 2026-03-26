from abc import ABC, abstractmethod
from typing import List

from src.models import Anomaly


class BaseAnalyzer(ABC):
    @abstractmethod
    async def analyze(self, **kwargs) -> List[Anomaly]:
        """Run analysis and return detected anomalies."""

    @abstractmethod
    async def update_model(self, **kwargs) -> None:
        """Update the ML model with new data."""
