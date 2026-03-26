import asyncio
import signal
import os

import structlog
import uvicorn

from src.agent import SREAgent
from src.api.routes import create_app
from src.config import Config


def setup_logging(log_level: str) -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer()
            if os.getenv("LOG_FORMAT") == "console"
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
    )


async def main() -> None:
    def _bool(key: str, default: str) -> bool:
        return os.getenv(key, default).lower() == "true"

    config = Config(
        elasticsearch_url=os.getenv("ELASTICSEARCH_URL", "http://elasticsearch:9200"),
        elasticsearch_username=os.getenv("ELASTICSEARCH_USERNAME", ""),
        elasticsearch_password=os.getenv("ELASTICSEARCH_PASSWORD", ""),
        elasticsearch_indices_metrics=os.getenv(
            "ELASTICSEARCH_INDICES_METRICS", "sre-metrics"
        ),
        elasticsearch_indices_logs=os.getenv("ELASTICSEARCH_INDICES_LOGS", "sre-logs"),
        elasticsearch_indices_anomalies=os.getenv(
            "ELASTICSEARCH_INDICES_ANOMALIES", "sre-anomalies"
        ),
        agent_analysis_interval=int(os.getenv("AGENT_ANALYSIS_INTERVAL", "300")),
        agent_log_level=os.getenv("AGENT_LOG_LEVEL", "INFO"),
        collectors_prometheus_enabled=_bool("COLLECTORS_PROMETHEUS_ENABLED", "true"),
        collectors_prometheus_url=os.getenv(
            "COLLECTORS_PROMETHEUS_URL", "http://prometheus-server:9090"
        ),
        collectors_metrics_server_enabled=_bool(
            "COLLECTORS_METRICS_SERVER_ENABLED", "true"
        ),
        collectors_k8s_api_enabled=_bool("COLLECTORS_K8S_API_ENABLED", "true"),
        collectors_k8s_api_watch_events=_bool("COLLECTORS_K8S_API_WATCH_EVENTS", "true"),
        thresholds_cpu_warning=float(os.getenv("THRESHOLDS_CPU_WARNING", "70")),
        thresholds_cpu_critical=float(os.getenv("THRESHOLDS_CPU_CRITICAL", "85")),
        thresholds_memory_warning=float(os.getenv("THRESHOLDS_MEMORY_WARNING", "70")),
        thresholds_memory_critical=float(os.getenv("THRESHOLDS_MEMORY_CRITICAL", "85")),
        thresholds_disk_warning=float(os.getenv("THRESHOLDS_DISK_WARNING", "80")),
        thresholds_disk_critical=float(os.getenv("THRESHOLDS_DISK_CRITICAL", "90")),
        ml_retrain_interval=int(os.getenv("ML_RETRAIN_INTERVAL", "3600")),
        ml_window_size=int(os.getenv("ML_WINDOW_SIZE", "100")),
        ml_anomaly_threshold=float(os.getenv("ML_ANOMALY_THRESHOLD", "0.05")),
        intelligence_enabled=_bool("INTELLIGENCE_ENABLED", "false"),
        intelligence_provider=os.getenv("INTELLIGENCE_PROVIDER", ""),
        intelligence_api_url=os.getenv("INTELLIGENCE_API_URL", ""),
        intelligence_api_key=os.getenv("INTELLIGENCE_API_KEY", ""),
        intelligence_model=os.getenv("INTELLIGENCE_MODEL", ""),
        alerter_alertmanager_enabled=_bool("ALERTER_ALERTMANAGER_ENABLED", "true"),
        alerter_alertmanager_url=os.getenv(
            "ALERTER_ALERTMANAGER_URL", "http://alertmanager:9093"
        ),
        alerter_fallback_webhook_enabled=_bool(
            "ALERTER_FALLBACK_WEBHOOK_ENABLED", "false"
        ),
        alerter_fallback_webhook_url=os.getenv("ALERTER_FALLBACK_WEBHOOK_URL", ""),
    )

    setup_logging(config.agent_log_level)
    logger = structlog.get_logger()
    logger.info("agent.starting")

    agent = SREAgent(config)
    app = create_app(config, agent)

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(agent.stop()))

    uvicorn_config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="warning")
    server = uvicorn.Server(uvicorn_config)

    await asyncio.gather(
        agent.start(),
        server.serve(),
    )


if __name__ == "__main__":
    asyncio.run(main())
