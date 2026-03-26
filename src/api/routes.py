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

    return app
