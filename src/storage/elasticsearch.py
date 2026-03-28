import structlog
from typing import Any, Dict, List, Optional

from elasticsearch import AsyncElasticsearch, NotFoundError
from elasticsearch.helpers import async_bulk

from src.config import Config
from src.models import StoredRecord
from src.storage.base import BaseStorage

logger = structlog.get_logger()


class ElasticsearchStorage(BaseStorage):
    def __init__(self, config: Config):
        self._config = config
        self._client: Optional[AsyncElasticsearch] = None

    async def connect(self) -> None:
        kwargs: Dict[str, Any] = {
            "hosts": [self._config.elasticsearch_url],
        }
        if self._config.elasticsearch_username and self._config.elasticsearch_password:
            kwargs["basic_auth"] = (
                self._config.elasticsearch_username,
                self._config.elasticsearch_password,
            )
        if not self._config.elasticsearch_verify_certs:
            kwargs["verify_certs"] = False
            kwargs["ssl_show_warn"] = False
        self._client = AsyncElasticsearch(**kwargs)
        info = await self._client.info()
        logger.info(
            "elasticsearch_storage.connected",
            version=info["version"]["number"],
        )

    async def ensure_indices(self, indices: List[str]) -> None:
        """Create kube-seer-owned indices if they do not exist."""
        if not self._client:
            return
        for index in indices:
            if not await self._client.indices.exists(index=index):
                await self._client.indices.create(index=index)
                logger.info("elasticsearch_storage.index_created", index=index)

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

    async def is_healthy(self) -> bool:
        if not self._client:
            return False
        try:
            return await self._client.ping()
        except Exception:
            return False

    async def store(self, index: str, record: StoredRecord) -> None:
        if not self._client:
            return
        doc = record.model_dump()
        try:
            await self._client.index(index=index, document=doc)
        except Exception as e:
            logger.error("elasticsearch_storage.store_error", index=index, error=str(e))

    async def store_bulk(self, index: str, records: List[StoredRecord]) -> int:
        if not self._client:
            return 0
        actions = [
            {
                "_index": index,
                "_source": r.model_dump(),
            }
            for r in records
        ]
        try:
            success, errors = await async_bulk(self._client, actions)
            if errors:
                error_count = len(errors) if isinstance(errors, list) else errors
                logger.warning(
                    "elasticsearch_storage.bulk_errors",
                    error_count=error_count,
                )
            return success
        except Exception as e:
            logger.error("elasticsearch_storage.bulk_error", index=index, error=str(e))
            return 0

    async def query(
        self,
        index: str,
        query_body: Dict[str, Any],
        size: int = 100,
    ) -> List[Dict[str, Any]]:
        if not self._client:
            return []
        try:
            result = await self._client.search(index=index, query=query_body, size=size)
            return [hit["_source"] for hit in result["hits"]["hits"]]
        except NotFoundError:
            logger.warning("elasticsearch_storage.index_not_found", index=index)
            return []
        except Exception as e:
            logger.error("elasticsearch_storage.query_error", index=index, error=str(e))
            return []
