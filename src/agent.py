"""
Agent IA SRE pour l'analyse des métriques et logs d'une stack EFK
"""

import asyncio
from datetime import datetime, UTC
from typing import List, Optional, Dict

import structlog
from elasticsearch import Elasticsearch
from kubernetes import client, config

from config import Config
from metrics_analyzer import MetricsAnalyzer
from log_analyzer import LogAnalyzer
from alerting import AlertManager
from models import Alert, Metric, LogEntry

logger = structlog.get_logger()


class SREAgent:
    """
    Agent IA principal pour l'analyse automatisée des métriques et logs EFK
    """

    def __init__(self, config: Config):
        self.config = config
        self.es_client: Optional[Elasticsearch] = None
        self.k8s_client = None
        self.metrics_analyzer = MetricsAnalyzer(config)
        self.log_analyzer = LogAnalyzer(config)
        self.alert_manager = AlertManager(config)
        self.running = False

    async def initialize(self):
        """Initialise les connexions aux services"""
        try:
            # Connexion Elasticsearch
            self.es_client = Elasticsearch(
                [self.config.elasticsearch_url],
                basic_auth=(
                    self.config.elasticsearch_user,
                    self.config.elasticsearch_password,
                ),
                verify_certs=False,
            )

            # Test de connexion ES
            if not self.es_client.ping():
                raise ConnectionError("Impossible de se connecter à Elasticsearch")

            # Connexion Kubernetes
            if self.config.k8s_in_cluster:
                config.load_incluster_config()
            else:
                config.load_kube_config()

            self.k8s_client = client.CoreV1Api()

            logger.info("Agent SRE initialisé avec succès")

        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation: {e}")
            raise

    async def run_analysis_cycle(self):
        """Execute un cycle complet d'analyse"""
        try:
            logger.info("Début du cycle d'analyse")

            # 1. Collecter les métriques
            metrics = await self.collect_metrics()

            # 2. Analyser les métriques pour détecter les anomalies
            metric_anomalies = await self.metrics_analyzer.analyze(metrics)

            # 3. Collecter et analyser les logs
            logs = await self.collect_logs()
            log_anomalies = await self.log_analyzer.analyze(logs)

            # 4. Corréler les anomalies
            correlated_alerts = await self.correlate_anomalies(
                metric_anomalies, log_anomalies
            )

            # 5. Générer et envoyer les alertes
            for alert in correlated_alerts:
                await self.alert_manager.send_alert(alert)

            # 6. Mettre à jour les modèles ML
            await self.update_models(metrics, logs)

            logger.info(
                f"Cycle d'analyse terminé - {len(correlated_alerts)} alertes générées"
            )

        except Exception as e:
            logger.error(f"Erreur durant le cycle d'analyse: {e}")
            await self.alert_manager.send_alert(
                Alert(
                    type="system_error",
                    severity="critical",
                    message=f"Erreur de l'agent SRE: {e}",
                    timestamp=datetime.now(UTC),
                )
            )

    async def collect_metrics(self) -> List[Metric]:
        """Collecte les métriques depuis Elasticsearch"""
        try:
            query = {
                "query": {
                    "bool": {
                        "must": [
                            {"range": {"@timestamp": {"gte": "now-5m"}}},
                            {"exists": {"field": "kubernetes.pod_name"}},
                        ]
                    }
                },
                "aggs": {
                    "pods": {
                        "terms": {"field": "kubernetes.pod_name.keyword"},
                        "aggs": {
                            "avg_cpu": {
                                "avg": {"field": "kubernetes.pod.cpu.usage.nanocores"}
                            },
                            "avg_memory": {
                                "avg": {"field": "kubernetes.pod.memory.usage.bytes"}
                            },
                            "max_cpu": {
                                "max": {"field": "kubernetes.pod.cpu.usage.nanocores"}
                            },
                            "max_memory": {
                                "max": {"field": "kubernetes.pod.memory.usage.bytes"}
                            },
                        },
                    }
                },
            }

            if not self.es_client:
                raise ConnectionError("Elasticsearch client not initialized")

            response = self.es_client.search(
                index=self.config.metrics_index, body=query, size=0
            )

            metrics = []
            for bucket in response["aggregations"]["pods"]["buckets"]:
                metrics.append(
                    Metric(
                        pod_name=bucket["key"],
                        cpu_usage=bucket["avg_cpu"]["value"],
                        memory_usage=bucket["avg_memory"]["value"],
                        cpu_peak=bucket["max_cpu"]["value"],
                        memory_peak=bucket["max_memory"]["value"],
                        timestamp=datetime.now(UTC),
                    )
                )

            return metrics

        except Exception as e:
            logger.error(f"Erreur lors de la collecte des métriques: {e}")
            return []

    async def collect_logs(self) -> List[LogEntry]:
        """Collecte les logs depuis Elasticsearch"""
        try:
            query = {
                "query": {
                    "bool": {
                        "must": [
                            {"range": {"@timestamp": {"gte": "now-5m"}}},
                            {"exists": {"field": "kubernetes.pod_name"}},
                        ],
                        "should": [
                            {"match": {"log": "error"}},
                            {"match": {"log": "exception"}},
                            {"match": {"log": "warning"}},
                            {"match": {"log": "critical"}},
                            {"match": {"log": "fatal"}},
                        ],
                        "minimum_should_match": 1,
                    }
                },
                "sort": [{"@timestamp": {"order": "desc"}}],
            }

            if not self.es_client:
                raise ConnectionError("Elasticsearch client not initialized")

            response = self.es_client.search(
                index=self.config.logs_index, body=query, size=1000
            )

            logs = []
            for hit in response["hits"]["hits"]:
                source = hit["_source"]
                logs.append(
                    LogEntry(
                        pod_name=source.get("kubernetes", {}).get("pod_name", ""),
                        namespace=source.get("kubernetes", {}).get(
                            "namespace_name", ""
                        ),
                        log_level=source.get("level", "INFO"),
                        message=source.get("log", ""),
                        timestamp=datetime.fromisoformat(
                            source.get("@timestamp", "").replace("Z", "+00:00")
                        ),
                    )
                )

            return logs

        except Exception as e:
            logger.error(f"Erreur lors de la collecte des logs: {e}")
            return []

    async def correlate_anomalies(
        self, metric_anomalies: List[Alert], log_anomalies: List[Alert]
    ) -> List[Alert]:
        """Corrèle les anomalies métriques et logs"""
        correlated_alerts = []

        # Grouper par pod/namespace
        metric_by_pod: Dict[str, List[Alert]] = {}
        for alert in metric_anomalies:
            pod = alert.metadata.get("pod_name", "")
            if pod not in metric_by_pod:
                metric_by_pod[pod] = []
            metric_by_pod[pod].append(alert)

        log_by_pod: Dict[str, List[Alert]] = {}
        for alert in log_anomalies:
            pod = alert.metadata.get("pod_name", "")
            if pod not in log_by_pod:
                log_by_pod[pod] = []
            log_by_pod[pod].append(alert)

        # Corréler par pod
        for pod in set(metric_by_pod.keys()) | set(log_by_pod.keys()):
            pod_metric_alerts = metric_by_pod.get(pod, [])
            pod_log_alerts = log_by_pod.get(pod, [])

            if pod_metric_alerts and pod_log_alerts:
                # Corrélation forte - problème critique
                correlated_alert = Alert(
                    type="correlated_issue",
                    severity="critical",
                    message=f"Problème corrélé détecté sur le pod {pod}: "
                    f"{len(pod_metric_alerts)} anomalies métriques, "
                    f"{len(pod_log_alerts)} anomalies logs",
                    timestamp=datetime.now(UTC),
                    metadata={
                        "pod_name": pod,
                        "metric_alerts": len(pod_metric_alerts),
                        "log_alerts": len(pod_log_alerts),
                        "correlation_score": 0.9,
                    },
                )
                correlated_alerts.append(correlated_alert)
            else:
                # Ajouter les alertes individuelles
                correlated_alerts.extend(pod_metric_alerts + pod_log_alerts)

        return correlated_alerts

    async def update_models(self, metrics: List[Metric], logs: List[LogEntry]):
        """Met à jour les modèles ML avec les nouvelles données"""
        try:
            # Mise à jour du modèle de détection d'anomalies métriques
            await self.metrics_analyzer.update_model(metrics)

            # Mise à jour du modèle d'analyse de logs
            await self.log_analyzer.update_model(logs)

        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour des modèles: {e}")

    async def start(self):
        """Démarre l'agent SRE"""
        await self.initialize()
        self.running = True

        logger.info("Agent SRE démarré")

        while self.running:
            try:
                await self.run_analysis_cycle()
                await asyncio.sleep(self.config.analysis_interval)

            except KeyboardInterrupt:
                logger.info("Arrêt demandé")
                break
            except Exception as e:
                logger.error(f"Erreur dans la boucle principale: {e}")
                await asyncio.sleep(30)  # Attendre avant de réessayer

    async def stop(self):
        """Arrête l'agent SRE"""
        self.running = False
        logger.info("Agent SRE arrêté")


async def main():
    """Point d'entrée principal"""
    config = Config()
    agent = SREAgent(config)

    try:
        await agent.start()
    except KeyboardInterrupt:
        await agent.stop()


if __name__ == "__main__":
    asyncio.run(main())
