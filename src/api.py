"""
API REST pour l'agent SRE
"""

import asyncio
import logging
from datetime import datetime, UTC
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from agent import SREAgent
from config import Config
from models import SystemHealth

logger = logging.getLogger(__name__)

app = FastAPI(
    title="EFK SRE Agent API",
    description="API REST pour l'agent IA SRE d'analyse EFK",
    version="1.0.0",
)

# Configuration CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Variables globales
agent: SREAgent = None
config: Config = None
start_time: datetime = datetime.now(UTC)


async def get_agent() -> SREAgent:
    """Dependency pour obtenir l'instance de l'agent"""
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent non initialisé")
    return agent


@app.on_event("startup")
async def startup_event():
    """Initialisation de l'API"""
    global agent, config, start_time

    try:
        config = Config()
        agent = SREAgent(config)
        await agent.initialize()
        start_time = datetime.now(UTC)

        logger.info("API SRE Agent démarrée")

        # Démarrer l'agent en arrière-plan
        asyncio.create_task(agent.start())

    except Exception as e:
        logger.error(f"Erreur lors du démarrage: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Arrêt propre de l'API"""
    global agent

    if agent:
        await agent.stop()
        logger.info("API SRE Agent arrêtée")


@app.get("/health")
async def health_check():
    """Point de santé de l'API"""
    return {
        "status": "healthy",
        "timestamp": datetime.now(UTC).isoformat(),
        "uptime": (datetime.now(UTC) - start_time).total_seconds(),
    }


@app.get("/status")
async def get_status(agent: SREAgent = Depends(get_agent)) -> SystemHealth:
    """Retourne le statut complet du système"""
    try:
        # Vérifier la connexion Elasticsearch
        es_status = "healthy" if agent.es_client.ping() else "unhealthy"

        # Vérifier Kubernetes
        try:
            agent.k8s_client.list_namespace()
            k8s_status = "healthy"
        except Exception:
            k8s_status = "unhealthy"

        # Statistiques des alertes
        alert_stats = agent.alert_manager.get_alert_stats()

        uptime = (datetime.now(UTC) - start_time).total_seconds()

        return SystemHealth(
            elasticsearch_status=es_status,
            kubernetes_status=k8s_status,
            agent_uptime=uptime,
            alerts_count_24h=alert_stats["last_24h"],
            last_analysis=datetime.now(UTC),
        )

    except Exception as e:
        logger.error(f"Erreur lors de la vérification du statut: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/alerts")
async def get_alerts(limit: int = 50, agent: SREAgent = Depends(get_agent)):
    """Retourne les alertes récentes"""
    try:
        alerts = agent.alert_manager.get_recent_alerts(limit)
        return {"alerts": [alert.to_dict() for alert in alerts], "total": len(alerts)}

    except Exception as e:
        logger.error(f"Erreur lors de la récupération des alertes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/alerts/stats")
async def get_alert_stats(agent: SREAgent = Depends(get_agent)):
    """Retourne les statistiques des alertes"""
    try:
        return agent.alert_manager.get_alert_stats()

    except Exception as e:
        logger.error(f"Erreur lors de la récupération des stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze/manual")
async def manual_analysis(agent: SREAgent = Depends(get_agent)):
    """Déclenche une analyse manuelle"""
    try:
        await agent.run_analysis_cycle()
        return {
            "status": "success",
            "message": "Analyse manuelle déclenchée",
            "timestamp": datetime.now(UTC).isoformat(),
        }

    except Exception as e:
        logger.error(f"Erreur lors de l'analyse manuelle: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/metrics/pods")
async def get_pod_metrics(agent: SREAgent = Depends(get_agent)):
    """Retourne les métriques actuelles des pods"""
    try:
        metrics = await agent.collect_metrics()
        return {
            "metrics": [metric.to_dict() for metric in metrics],
            "count": len(metrics),
            "timestamp": datetime.now(UTC).isoformat(),
        }

    except Exception as e:
        logger.error(f"Erreur lors de la collecte des métriques: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/logs/recent")
async def get_recent_logs(agent: SREAgent = Depends(get_agent)):
    """Retourne les logs récents avec erreurs"""
    try:
        logs = await agent.collect_logs()
        return {
            "logs": [log.to_dict() for log in logs],
            "count": len(logs),
            "timestamp": datetime.now(UTC).isoformat(),
        }

    except Exception as e:
        logger.error(f"Erreur lors de la collecte des logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/config")
async def get_config():
    """Retourne la configuration (sans les secrets)"""
    try:
        config_dict = {
            "elasticsearch_url": config.elasticsearch_url,
            "metrics_index": config.metrics_index,
            "logs_index": config.logs_index,
            "analysis_interval": config.analysis_interval,
            "cpu_threshold_warning": config.cpu_threshold_warning,
            "cpu_threshold_critical": config.cpu_threshold_critical,
            "memory_threshold_warning": config.memory_threshold_warning,
            "memory_threshold_critical": config.memory_threshold_critical,
            "log_level": config.log_level,
        }
        return config_dict

    except Exception as e:
        logger.error(f"Erreur lors de la récupération de la config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/models/retrain")
async def retrain_models(agent: SREAgent = Depends(get_agent)):
    """Force le réentraînement des modèles ML"""
    try:
        # Collecter des données récentes
        metrics = await agent.collect_metrics()
        logs = await agent.collect_logs()

        # Mettre à jour les modèles
        await agent.update_models(metrics, logs)

        return {
            "status": "success",
            "message": "Modèles réentraînés",
            "metrics_count": len(metrics),
            "logs_count": len(logs),
            "timestamp": datetime.now(UTC).isoformat(),
        }

    except Exception as e:
        logger.error(f"Erreur lors du réentraînement: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def run_api(host: str = "0.0.0.0", port: int = 8080):
    """Lance l'API REST"""
    uvicorn.run("src.api:app", host=host, port=port, log_level="info", reload=False)


if __name__ == "__main__":
    run_api()
