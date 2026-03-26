import asyncio
from datetime import datetime, timezone
from typing import Optional

import structlog

from src.collector.k8s_api import KubernetesApiCollector
from src.collector.metrics_server import MetricsServerCollector
from src.collector.prometheus import PrometheusCollector
from src.config import Config
from src.models import CollectedData, StoredRecord
from src.storage.elasticsearch import ElasticsearchStorage

logger = structlog.get_logger()


class SREAgent:
    def __init__(self, config: Config):
        self._config = config
        self._running = False

        self._prometheus: Optional[PrometheusCollector] = (
            PrometheusCollector(config) if config.collectors_prometheus_enabled else None
        )
        self._metrics_server: Optional[MetricsServerCollector] = (
            MetricsServerCollector(config) if config.collectors_metrics_server_enabled else None
        )
        self._k8s_api: Optional[KubernetesApiCollector] = (
            KubernetesApiCollector(config) if config.collectors_k8s_api_enabled else None
        )
        self._storage = ElasticsearchStorage(config)

    async def initialize(self) -> None:
        logger.info("agent.initializing")
        await self._storage.connect()
        if self._prometheus:
            await self._prometheus.connect()
        if self._metrics_server:
            await self._metrics_server.connect()
        if self._k8s_api:
            await self._k8s_api.connect()
        logger.info("agent.initialized")

    async def collect(self) -> CollectedData:
        now = datetime.now(timezone.utc)
        node_metrics = []
        pod_metrics = []
        events = []
        resource_states = []

        if self._prometheus:
            try:
                node_metrics.extend(await self._prometheus.collect_node_metrics())
                pod_metrics.extend(await self._prometheus.collect_pod_metrics())
            except Exception as e:
                logger.error("agent.prometheus_error", error=str(e))

        if self._metrics_server:
            try:
                ms_nodes = await self._metrics_server.collect_node_metrics()
                ms_pods = await self._metrics_server.collect_pod_metrics()
                existing_node_names = {n.node_name for n in node_metrics}
                for n in ms_nodes:
                    if n.node_name not in existing_node_names:
                        node_metrics.append(n)
                existing_pod_names = {p.pod_name for p in pod_metrics}
                for p in ms_pods:
                    if p.pod_name not in existing_pod_names:
                        pod_metrics.append(p)
            except Exception as e:
                logger.error("agent.metrics_server_error", error=str(e))

        if self._k8s_api:
            try:
                events = await self._k8s_api.collect_events()
                resource_states = await self._k8s_api.collect_resource_states()
            except Exception as e:
                logger.error("agent.k8s_api_error", error=str(e))

        logger.info(
            "agent.collected",
            nodes=len(node_metrics),
            pods=len(pod_metrics),
            events=len(events),
            resources=len(resource_states),
        )
        return CollectedData(
            node_metrics=node_metrics,
            pod_metrics=pod_metrics,
            events=events,
            resource_states=resource_states,
            collection_timestamp=now,
        )

    async def store(self, data: CollectedData) -> None:
        metrics_index = self._config.elasticsearch_indices_metrics

        records = []
        for node in data.node_metrics:
            records.append(
                StoredRecord(
                    record_type="node_metrics",
                    data=node.model_dump(),
                    timestamp=data.collection_timestamp,
                )
            )
        for pod in data.pod_metrics:
            records.append(
                StoredRecord(
                    record_type="pod_metrics",
                    data=pod.model_dump(),
                    timestamp=data.collection_timestamp,
                )
            )
        for event in data.events:
            records.append(
                StoredRecord(
                    record_type="k8s_event",
                    data=event.model_dump(),
                    timestamp=data.collection_timestamp,
                )
            )
        for state in data.resource_states:
            records.append(
                StoredRecord(
                    record_type="resource_state",
                    data=state.model_dump(),
                    timestamp=data.collection_timestamp,
                )
            )

        if records:
            stored = await self._storage.store_bulk(metrics_index, records)
            logger.info("agent.stored", count=stored)

    async def run_cycle(self) -> None:
        logger.info("agent.cycle_start")
        data = await self.collect()
        await self.store(data)
        logger.info("agent.cycle_end")

    async def start(self) -> None:
        await self.initialize()
        self._running = True
        logger.info("agent.started", interval=self._config.agent_analysis_interval)
        while self._running:
            try:
                await self.run_cycle()
            except Exception as e:
                logger.error("agent.cycle_error", error=str(e))
            await asyncio.sleep(self._config.agent_analysis_interval)

    async def stop(self) -> None:
        self._running = False
        await self._storage.close()
        if self._prometheus:
            await self._prometheus.close()
        if self._metrics_server:
            await self._metrics_server.close()
        if self._k8s_api:
            await self._k8s_api.close()
        logger.info("agent.stopped")
