import asyncio
from datetime import datetime, timezone
from typing import List, Optional

import structlog

from src.analyzer.correlator import Correlator
from src.analyzer.predictor import Predictor
from src.analyzer.events import EventAnalyzer
from src.analyzer.logs import LogAnalyzer
from src.analyzer.metrics import MetricsAnalyzer
from src.analyzer.resources import ResourceStateAnalyzer
from src.collector.k8s_api import KubernetesApiCollector
from src.collector.metrics_server import MetricsServerCollector
from src.collector.prometheus import PrometheusCollector
from src.config import Config
from src.models import AnalysisResult, Anomaly, CollectedData, StoredRecord
from src.alerter.service import AlerterService
from src.storage.elasticsearch import ElasticsearchStorage

logger = structlog.get_logger()


def _dated_index(base: str) -> str:
    """Append today's UTC date to an index name: 'sre-metrics' → 'sre-metrics-2026.03.28'."""
    return f"{base}-{datetime.now(timezone.utc).strftime('%Y.%m.%d')}"


class SREAgent:
    def __init__(self, config: Config):
        self._config = config
        self._running = False

        self._prometheus: Optional[PrometheusCollector] = (
            PrometheusCollector(config)
            if config.collectors_prometheus_enabled
            else None
        )
        self._metrics_server: Optional[MetricsServerCollector] = (
            MetricsServerCollector(config)
            if config.collectors_metrics_server_enabled
            else None
        )
        self._k8s_api: Optional[KubernetesApiCollector] = (
            KubernetesApiCollector(config)
            if config.collectors_k8s_api_enabled
            else None
        )
        self._storage = ElasticsearchStorage(config)
        self._metrics_analyzer = MetricsAnalyzer(config)
        self._event_analyzer = EventAnalyzer(config)
        self._log_analyzer = LogAnalyzer(config, self._storage)
        self._resource_analyzer = ResourceStateAnalyzer(config)
        self._correlator = Correlator(config)
        self._predictor = Predictor(config)
        self._last_analysis: Optional[AnalysisResult] = None
        self._alerter = AlerterService(config)

    async def initialize(self) -> None:
        logger.info("agent.initializing")
        await self._storage.connect()
        await self._storage.ensure_indices(
            [
                _dated_index(self._config.elasticsearch_indices_metrics),
                _dated_index(self._config.elasticsearch_indices_anomalies),
            ]
        )
        if self._prometheus:
            await self._prometheus.connect()
        if self._metrics_server:
            await self._metrics_server.connect()
        if self._k8s_api:
            await self._k8s_api.connect()
        await self._alerter.connect()
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
                existing_pods = {(p.namespace, p.pod_name) for p in pod_metrics}
                for p in ms_pods:
                    if (p.namespace, p.pod_name) not in existing_pods:
                        pod_metrics.append(p)
            except Exception as e:
                logger.error("agent.metrics_server_error", error=str(e))

        if self._k8s_api:
            try:
                events = await self._k8s_api.collect_events()
                resource_states = await self._k8s_api.collect_resource_states()
            except Exception as e:
                logger.error("agent.k8s_api_error", error=str(e))

        if self._k8s_api:
            try:
                pod_limits = await self._k8s_api.collect_pod_limits()
                pod_metrics = [
                    pod.model_copy(
                        update={
                            "cpu_limit_millicores": pod_limits.get(
                                (pod.namespace, pod.pod_name), (None, None)
                            )[0],
                            "memory_limit_bytes": pod_limits.get(
                                (pod.namespace, pod.pod_name), (None, None)
                            )[1],
                        }
                    )
                    for pod in pod_metrics
                ]
            except Exception as e:
                logger.error("agent.pod_limits_error", error=str(e))

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
        metrics_index = _dated_index(self._config.elasticsearch_indices_metrics)

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

    async def analyze(self, data: CollectedData) -> AnalysisResult:
        anomalies: List[Anomaly] = []
        try:
            metrics_anomalies = await self._metrics_analyzer.analyze(
                node_metrics=data.node_metrics,
                pod_metrics=data.pod_metrics,
            )
            anomalies.extend(metrics_anomalies)
        except Exception as e:
            logger.error("agent.metrics_analysis_error", error=str(e))

        try:
            event_anomalies = await self._event_analyzer.analyze(
                events=data.events,
            )
            anomalies.extend(event_anomalies)
        except Exception as e:
            logger.error("agent.event_analysis_error", error=str(e))

        try:
            log_anomalies = await self._log_analyzer.analyze()
            anomalies.extend(log_anomalies)
        except Exception as e:
            logger.error("agent.log_analysis_error", error=str(e))

        try:
            resource_anomalies = await self._resource_analyzer.analyze(
                resource_states=data.resource_states,
            )
            anomalies.extend(resource_anomalies)
        except Exception as e:
            logger.error("agent.resource_analysis_error", error=str(e))

        try:
            incidents = await self._correlator.correlate(anomalies=anomalies, data=data)
        except Exception as e:
            logger.error("agent.correlation_error", error=str(e))
            incidents = []

        try:
            predictions, policy_anomalies = await self._predictor.predict(
                node_metrics=data.node_metrics,
                pod_metrics=data.pod_metrics,
            )
            anomalies.extend(policy_anomalies)
        except Exception as e:
            logger.error("agent.prediction_error", error=str(e))
            predictions = []

        result = AnalysisResult(
            anomalies=anomalies,
            incidents=incidents,
            predictions=predictions,
            analysis_timestamp=data.collection_timestamp,
            metrics_analyzed=len(data.node_metrics) + len(data.pod_metrics),
            logs_analyzed=0,
            events_analyzed=len(data.events),
        )
        self._last_analysis = result
        logger.info("agent.analyzed", anomaly_count=len(anomalies))
        return result

    async def store_anomalies(self, result: AnalysisResult) -> None:
        if not result.anomalies:
            return
        index = _dated_index(self._config.elasticsearch_indices_anomalies)
        records = [
            StoredRecord(
                record_type="anomaly",
                data=a.model_dump(),
                timestamp=a.timestamp,
            )
            for a in result.anomalies
        ]
        stored = await self._storage.store_bulk(index, records)
        logger.info("agent.anomalies_stored", count=stored)
        if result.predictions:
            pred_records = [
                StoredRecord(
                    record_type="prediction",
                    data=p.model_dump(),
                    timestamp=p.timestamp,
                )
                for p in result.predictions
            ]
            stored = await self._storage.store_bulk(index, pred_records)
            logger.info("agent.predictions_stored", count=stored)

    async def update_models(self, data: CollectedData) -> None:
        try:
            await self._metrics_analyzer.update_model(
                node_metrics=data.node_metrics,
                pod_metrics=data.pod_metrics,
            )
        except Exception as e:
            logger.error("agent.model_update_error", error=str(e))
        try:
            await self._log_analyzer.update_model()
        except Exception as e:
            logger.error("agent.log_model_update_error", error=str(e))
        try:
            await self._predictor.update(
                node_metrics=data.node_metrics,
                pod_metrics=data.pod_metrics,
            )
        except Exception as e:
            logger.error("agent.predictor_update_error", error=str(e))

    async def run_cycle(self) -> None:
        logger.info("agent.cycle_start")
        data = await self.collect()
        await self.store(data)
        result = await self.analyze(data)
        await self.store_anomalies(result)
        await self._alerter.send_alerts(result)
        await self.update_models(data)
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
        await self._alerter.close()
        logger.info("agent.stopped")
