from abc import ABC, abstractmethod
from typing import Any, Dict, List

from src.models import StoredRecord


class BaseStorage(ABC):
    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the storage backend."""

    @abstractmethod
    async def close(self) -> None:
        """Close connection to the storage backend."""

    @abstractmethod
    async def is_healthy(self) -> bool:
        """Check if the storage backend is reachable."""

    @abstractmethod
    async def store(self, index: str, record: StoredRecord) -> None:
        """Store a single record."""

    @abstractmethod
    async def store_bulk(self, index: str, records: List[StoredRecord]) -> int:
        """Store multiple records. Returns the number of successfully stored records."""

    @abstractmethod
    async def query(
        self,
        index: str,
        query_body: Dict[str, Any],
        size: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query records from the storage backend."""

    @abstractmethod
    async def aggregate(
        self,
        index: str,
        query_body: Dict[str, Any],
        aggs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run an aggregation query. Returns the `aggregations` dict from the response."""
