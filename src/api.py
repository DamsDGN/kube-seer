"""
API REST pour l'agent SRE
"""

import asyncio
import logging
import os
from datetime import datetime, UTC
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

from .agent import SREAgent
from .config import Config
from .models import SystemHealth

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

# Servir les fichiers statiques (dashboard web)
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Variables globales
agent: Optional[SREAgent] = None
config: Optional[Config] = None
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
    if agent:
        await agent.stop()
        logger.info("API SRE Agent arrêtée")


@app.get("/")
async def root():
    """Redirection vers le dashboard"""
    return FileResponse(os.path.join(static_dir, "dashboard.html"))


@app.get("/dashboard")
async def dashboard():
    """Interface web du dashboard"""
    return FileResponse(os.path.join(static_dir, "dashboard.html"))


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
        es_status = "healthy" if agent.es_client and agent.es_client.ping() else "unhealthy"

        # Vérifier Kubernetes
        try:
            if agent.k8s_client:
                agent.k8s_client.list_namespace()
                k8s_status = "healthy"
            else:
                k8s_status = "unhealthy"
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


@app.get("/llm/status")
async def get_llm_status():
    """Retourne le statut de la fonctionnalité LLM"""
    try:
        return {
            "enabled": config.llm_enabled,
            "provider": config.llm_provider if config.llm_enabled else None,
            "model": config.llm_model if config.llm_enabled else None,
            "status": "active" if config.llm_enabled else "disabled",
        }
    except Exception as e:
        logger.error(f"Erreur lors de la vérification du statut LLM: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/alerts/{alert_id}/enhance")
async def enhance_alert(alert_id: str, agent: SREAgent = Depends(get_agent)):
    """Améliore l'interprétation d'une alerte avec le LLM"""
    try:
        # Récupérer l'alerte depuis l'historique
        alert = None
        for a in agent.alert_manager.alert_history:
            if hasattr(a, "uuid") and str(a.uuid) == alert_id:
                alert = a
                break

        if not alert:
            raise HTTPException(status_code=404, detail="Alerte non trouvée")

        # Construire le contexte
        context = {}
        if hasattr(alert, "metadata") and alert.metadata:
            context.update(alert.metadata)

        # Améliorer avec le LLM
        enhanced_analysis = await agent.enhance_alert_with_llm(alert, context)

        return {
            "alert_id": alert_id,
            "analysis": enhanced_analysis,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de l'amélioration de l'alerte: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/alerts/{alert_id}/troubleshoot")
async def get_troubleshooting(alert_id: str, agent: SREAgent = Depends(get_agent)):
    """Génère un guide de dépannage pour une alerte"""
    try:
        # Récupérer l'alerte
        alert = None
        for a in agent.alert_manager.alert_history:
            if str(id(a)) == alert_id:
                alert = a
                break

        if not alert:
            raise HTTPException(status_code=404, detail="Alerte non trouvée")

        # Générer le guide de dépannage
        guidance = await agent.get_troubleshooting_guidance(alert)

        return {
            "alert_id": alert_id,
            "troubleshooting": guidance,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la génération du guide: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/logs/patterns")
async def analyze_log_patterns(limit: int = 50, agent: SREAgent = Depends(get_agent)):
    """Analyse les patterns dans les logs récents avec le LLM"""
    try:
        # Collecter les logs récents
        logs = await agent.collect_logs()

        # Limiter le nombre de logs
        if limit and len(logs) > limit:
            logs = logs[-limit:]

        # Analyser avec le LLM
        patterns_analysis = await agent.analyze_log_patterns_with_llm(logs)

        return {
            "patterns_analysis": patterns_analysis,
            "logs_analyzed": len(logs),
            "timestamp": datetime.now(UTC).isoformat(),
        }

    except Exception as e:
        logger.error(f"Erreur lors de l'analyse des patterns: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/alerts/enhanced")
async def get_enhanced_alerts(limit: int = 10, agent: SREAgent = Depends(get_agent)):
    """Retourne les alertes récentes avec analyse LLM enrichie"""
    try:
        recent_alerts = (
            agent.alert_manager.alert_history[-limit:] if agent.alert_manager.alert_history else []
        )
        enhanced_alerts = []

        for alert in recent_alerts:
            try:
                # Construire le contexte basique
                context = {}
                if hasattr(alert, "metadata") and alert.metadata:
                    context.update(alert.metadata)

                # Améliorer avec le LLM
                enhanced_analysis = await agent.enhance_alert_with_llm(alert, context)

                enhanced_alerts.append(
                    {
                        "alert": alert.to_dict(),
                        "enhanced_analysis": enhanced_analysis,
                        "alert_id": str(id(alert)),
                    }
                )
            except Exception as e:
                logger.warning(f"Erreur lors de l'amélioration de l'alerte {alert.type}: {e}")
                # Ajouter l'alerte sans amélioration
                enhanced_alerts.append(
                    {
                        "alert": alert.to_dict(),
                        "enhanced_analysis": {"enhanced": False, "error": str(e)},
                        "alert_id": str(id(alert)),
                    }
                )

        return {
            "alerts": enhanced_alerts,
            "total": len(enhanced_alerts),
            "llm_enabled": config.llm_enabled if config else False,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    except Exception as e:
        logger.error(f"Erreur lors de la récupération des alertes enrichies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def run_api(host: str = "0.0.0.0", port: int = 8080):
    """Lance l'API REST"""
    uvicorn.run("src.api:app", host=host, port=port, log_level="info", reload=False)


if __name__ == "__main__":
    run_api()
