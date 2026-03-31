from typing import List

from pydantic import BaseModel, field_validator, model_validator


class Config(BaseModel):
    # Elasticsearch
    elasticsearch_url: str
    elasticsearch_username: str = ""
    elasticsearch_password: str = ""
    elasticsearch_secret_ref: str = ""
    elasticsearch_verify_certs: bool = True
    elasticsearch_indices_metrics: str = "sre-metrics"
    elasticsearch_indices_logs: str = "sre-logs"
    elasticsearch_indices_anomalies: str = "sre-anomalies"

    # Agent
    agent_analysis_interval: int = 300
    agent_log_level: str = "INFO"

    # Collectors
    collectors_prometheus_enabled: bool = True
    collectors_prometheus_url: str = "http://prometheus-server:9090"
    collectors_metrics_server_enabled: bool = True
    collectors_k8s_api_enabled: bool = True
    collectors_k8s_api_watch_events: bool = True

    # Thresholds
    thresholds_cpu_warning: float = 70.0
    thresholds_cpu_critical: float = 85.0
    thresholds_memory_warning: float = 70.0
    thresholds_memory_critical: float = 85.0
    thresholds_disk_warning: float = 80.0
    thresholds_disk_critical: float = 90.0

    # ML
    ml_retrain_interval: int = 3600
    ml_window_size: int = 100
    ml_anomaly_threshold: float = 0.05

    # Prediction
    prediction_horizon_hours: int = 168

    # Intelligence (optional LLM)
    intelligence_enabled: bool = False
    intelligence_provider: str = ""
    intelligence_api_url: str = ""
    intelligence_api_key: str = ""
    intelligence_api_key_secret_ref: str = ""
    intelligence_model: str = ""

    # Alerter
    alerter_alertmanager_enabled: bool = True
    alerter_alertmanager_url: str = "http://alertmanager:9093"
    alerter_fallback_webhook_enabled: bool = False
    alerter_fallback_webhook_url: str = ""

    # Exclusions (comma-separated strings parsed into lists)
    exclusions_namespaces: List[str] = []
    exclusions_deployments: List[str] = []
    exclusions_statefulsets: List[str] = []
    exclusions_daemonsets: List[str] = []
    exclusions_pods: List[str] = []

    @field_validator(
        "exclusions_namespaces",
        "exclusions_deployments",
        "exclusions_statefulsets",
        "exclusions_daemonsets",
        "exclusions_pods",
        mode="before",
    )
    @classmethod
    def parse_csv(cls, v: object) -> List[str]:
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        if isinstance(v, list):
            return v
        return []

    @model_validator(mode="after")
    def validate_config(self) -> "Config":
        if not self.elasticsearch_url:
            raise ValueError("elasticsearch_url is required")
        if self.agent_analysis_interval < 60:
            raise ValueError("agent_analysis_interval must be >= 60 seconds")
        if not (0 < self.ml_anomaly_threshold < 1):
            raise ValueError("ml_anomaly_threshold must be between 0 and 1")
        if self.thresholds_cpu_warning >= self.thresholds_cpu_critical:
            raise ValueError("cpu warning threshold must be less than critical")
        if self.thresholds_memory_warning >= self.thresholds_memory_critical:
            raise ValueError("memory warning threshold must be less than critical")
        if self.thresholds_disk_warning >= self.thresholds_disk_critical:
            raise ValueError("disk warning threshold must be less than critical")
        return self
