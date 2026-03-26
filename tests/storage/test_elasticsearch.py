import pytest
from unittest.mock import AsyncMock, patch

from src.storage.elasticsearch import ElasticsearchStorage
from src.config import Config
from src.models import StoredRecord


@pytest.fixture
def config():
    return Config(
        elasticsearch_url="http://localhost:9200",
        elasticsearch_username="elastic",
        elasticsearch_password="changeme",
    )


@pytest.fixture
def storage(config):
    return ElasticsearchStorage(config)


class TestElasticsearchConnect:
    @pytest.mark.asyncio
    async def test_connect(self, storage):
        with patch("src.storage.elasticsearch.AsyncElasticsearch") as mock_es_cls:
            mock_es = AsyncMock()
            mock_es.info = AsyncMock(return_value={"version": {"number": "8.0.0"}})
            mock_es_cls.return_value = mock_es
            await storage.connect()
            assert storage._client is not None


class TestElasticsearchHealthy:
    @pytest.mark.asyncio
    async def test_is_healthy_true(self, storage):
        storage._client = AsyncMock()
        storage._client.ping = AsyncMock(return_value=True)
        assert await storage.is_healthy() is True

    @pytest.mark.asyncio
    async def test_is_healthy_false(self, storage):
        assert await storage.is_healthy() is False


class TestElasticsearchStore:
    @pytest.mark.asyncio
    async def test_store_single(self, storage, sample_timestamp):
        storage._client = AsyncMock()
        storage._client.index = AsyncMock(return_value={"result": "created"})

        record = StoredRecord(
            record_type="node_metrics",
            data={"node_name": "node-1", "cpu": 45.2},
            timestamp=sample_timestamp,
            cluster_name="prod",
        )
        await storage.store("sre-metrics", record)
        storage._client.index.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_bulk(self, storage, sample_timestamp):
        storage._client = AsyncMock()

        with patch("src.storage.elasticsearch.async_bulk") as mock_bulk:
            mock_bulk.return_value = (2, [])
            records = [
                StoredRecord(
                    record_type="node_metrics",
                    data={"node_name": "node-1"},
                    timestamp=sample_timestamp,
                    cluster_name="prod",
                ),
                StoredRecord(
                    record_type="node_metrics",
                    data={"node_name": "node-2"},
                    timestamp=sample_timestamp,
                    cluster_name="prod",
                ),
            ]
            count = await storage.store_bulk("sre-metrics", records)
            assert count == 2


class TestElasticsearchQuery:
    @pytest.mark.asyncio
    async def test_query(self, storage):
        storage._client = AsyncMock()
        storage._client.search = AsyncMock(
            return_value={
                "hits": {
                    "hits": [
                        {"_source": {"record_type": "node_metrics", "data": {"cpu": 45}}},
                        {"_source": {"record_type": "node_metrics", "data": {"cpu": 60}}},
                    ]
                }
            }
        )

        results = await storage.query("sre-metrics", {"match_all": {}})
        assert len(results) == 2
        assert results[0]["record_type"] == "node_metrics"
