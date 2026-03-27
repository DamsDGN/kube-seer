from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from src.config import Config

SECRETS_FIELDS = {
    "elasticsearch_password",
    "elasticsearch_secret_ref",
    "intelligence_api_key",
    "intelligence_api_key_secret_ref",
}


def create_app(config: Config, agent) -> FastAPI:
    app = FastAPI(title="EFK SRE Agent", version="2.0.0")
    start_time = datetime.now(timezone.utc)

    @app.get("/health")
    async def health():
        uptime = (datetime.now(timezone.utc) - start_time).total_seconds()
        return {"status": "ok", "uptime_seconds": uptime}

    @app.get("/ready")
    async def ready():
        es_ok = await agent._storage.is_healthy()
        prom_ok = True
        if agent._prometheus:
            prom_ok = await agent._prometheus.is_healthy()

        all_ready = es_ok and prom_ok
        status_code = 200 if all_ready else 503
        return JSONResponse(
            status_code=status_code,
            content={
                "ready": all_ready,
                "elasticsearch": es_ok,
                "prometheus": prom_ok,
            },
        )

    @app.get("/status")
    async def status():
        es_ok = await agent._storage.is_healthy()
        prom_ok = False
        ms_ok = False
        k8s_ok = False
        if agent._prometheus:
            prom_ok = await agent._prometheus.is_healthy()
        if agent._metrics_server:
            ms_ok = await agent._metrics_server.is_healthy()
        if agent._k8s_api:
            k8s_ok = await agent._k8s_api.is_healthy()

        return {
            "agent_running": agent._running,
            "uptime_seconds": (datetime.now(timezone.utc) - start_time).total_seconds(),
            "elasticsearch": es_ok,
            "prometheus": prom_ok,
            "metrics_server": ms_ok,
            "kubernetes_api": k8s_ok,
        }

    @app.get("/config")
    async def get_config():
        config_dict = config.model_dump()
        return {k: v for k, v in config_dict.items() if k not in SECRETS_FIELDS}

    @app.get("/anomalies")
    async def get_anomalies(
        severity: str = "",
        namespace: str = "",
        limit: int = 100,
    ):
        query_parts: list = [{"match": {"record_type": "anomaly"}}]
        if severity:
            severity_map = {"info": 0, "warning": 1, "critical": 2}
            sev_val = severity_map.get(severity.lower())
            if sev_val is not None:
                query_parts.append({"match": {"data.severity": sev_val}})
        if namespace:
            query_parts.append({"match": {"data.namespace": namespace}})

        query_body = {"bool": {"must": query_parts}}
        results = await agent._storage.query(
            index=config.elasticsearch_indices_anomalies,
            query_body=query_body,
            size=limit,
        )
        return {"anomalies": results, "count": len(results)}

    @app.post("/analyze")
    async def trigger_analysis():
        await agent.run_cycle()
        result = agent._last_analysis
        if result:
            return {
                "status": "completed",
                "anomalies_found": len(result.anomalies),
                "metrics_analyzed": result.metrics_analyzed,
                "events_analyzed": result.events_analyzed,
                "timestamp": result.analysis_timestamp.isoformat(),
            }
        return {"status": "completed", "anomalies_found": 0}

    @app.get("/alerts/stats")
    async def alert_stats():
        if hasattr(agent, "_alerter") and agent._alerter:
            return agent._alerter.get_stats()
        return {
            "total_sent": 0,
            "alertmanager_sent": 0,
            "webhook_sent": 0,
            "deduped": 0,
            "skipped_info": 0,
        }

    @app.get("/incidents")
    async def get_incidents():
        if agent._last_analysis and agent._last_analysis.incidents:
            return {
                "incidents": [
                    inc.model_dump() for inc in agent._last_analysis.incidents
                ],
                "count": len(agent._last_analysis.incidents),
            }
        return {"incidents": [], "count": 0}

    @app.get("/predictions")
    async def get_predictions():
        if agent._last_analysis and agent._last_analysis.predictions:
            return {
                "predictions": [
                    p.model_dump() for p in agent._last_analysis.predictions
                ],
                "count": len(agent._last_analysis.predictions),
            }
        return {"predictions": [], "count": 0}

    return app
