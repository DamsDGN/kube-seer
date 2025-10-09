"""
Configuration de l'agent SRE
"""

import os
from dataclasses import dataclass


@dataclass
class Config:
    """Configuration de l'agent SRE"""

    def __init__(self):
        """Initialise la configuration à partir des variables d'environnement"""

        # Elasticsearch
        self.elasticsearch_url = os.getenv("ELASTICSEARCH_URL", "http://elasticsearch:9200")
        self.elasticsearch_user = os.getenv("ELASTICSEARCH_USER", "elastic")
        self.elasticsearch_password = os.getenv("ELASTICSEARCH_PASSWORD", "")

        # Index Elasticsearch
        self.metrics_index = os.getenv("METRICS_INDEX", "metricbeat-*")
        self.logs_index = os.getenv("LOGS_INDEX", "fluentd-*")

        # Kubernetes
        self.k8s_in_cluster = os.getenv("K8S_IN_CLUSTER", "true").lower() == "true"
        self.k8s_namespace = os.getenv("K8S_NAMESPACE", "default")

        # Analyse
        self.analysis_interval = int(os.getenv("ANALYSIS_INTERVAL", "300"))  # 5 minutes
        self.anomaly_threshold = float(os.getenv("ANOMALY_THRESHOLD", "0.05"))

        # Seuils d'alerte
        self.cpu_threshold_warning = float(os.getenv("CPU_THRESHOLD_WARNING", "70.0"))
        self.cpu_threshold_critical = float(os.getenv("CPU_THRESHOLD_CRITICAL", "85.0"))
        self.memory_threshold_warning = float(os.getenv("MEMORY_THRESHOLD_WARNING", "70.0"))
        self.memory_threshold_critical = float(os.getenv("MEMORY_THRESHOLD_CRITICAL", "85.0"))

        # Alerting
        self.webhook_url = os.getenv("WEBHOOK_URL")
        self.slack_webhook = os.getenv("SLACK_WEBHOOK")
        self.email_smtp_server = os.getenv("EMAIL_SMTP_SERVER", "")
        self.email_smtp_port = int(os.getenv("EMAIL_SMTP_PORT", "587"))
        self.email_username = os.getenv("EMAIL_USERNAME", "")
        self.email_password = os.getenv("EMAIL_PASSWORD", "")
        self.email_recipients = os.getenv("EMAIL_RECIPIENTS", "")

        # Logging
        self.log_level = os.getenv("LOG_LEVEL", "INFO")

        # Modèles ML
        self.model_retrain_interval = int(os.getenv("MODEL_RETRAIN_INTERVAL", "3600"))  # 1 heure
        self.model_window_size = int(os.getenv("MODEL_WINDOW_SIZE", "100"))

        # Configuration LLM (optionnel)
        self.llm_enabled = os.getenv("LLM_ENABLED", "false").lower() == "true"
        self.llm_provider = os.getenv("LLM_PROVIDER", "openai")  # openai, anthropic, ollama
        self.llm_api_key = os.getenv("LLM_API_KEY", "")
        self.llm_model = os.getenv("LLM_MODEL", "gpt-3.5-turbo")
        self.llm_base_url = os.getenv("LLM_BASE_URL", "")  # Pour Ollama ou autres APIs
        self.llm_max_tokens = int(os.getenv("LLM_MAX_TOKENS", "1000"))
        self.llm_temperature = float(os.getenv("LLM_TEMPERATURE", "0.1"))

        # Validation
        self._validate()

    def _validate(self):
        """Validation de la configuration"""
        if self.analysis_interval < 60:
            raise ValueError("ANALYSIS_INTERVAL doit être au moins 60 secondes")

        if self.cpu_threshold_warning >= self.cpu_threshold_critical:
            raise ValueError("CPU warning threshold doit être inférieur au threshold critique")

        if self.memory_threshold_warning >= self.memory_threshold_critical:
            raise ValueError("Memory warning threshold doit être inférieur au threshold critique")

        # Validation LLM
        if self.llm_enabled:
            if self.llm_provider == "openai" and not self.llm_api_key:
                raise ValueError("LLM_API_KEY est requis pour le provider OpenAI")
            if self.llm_provider == "anthropic" and not self.llm_api_key:
                raise ValueError("LLM_API_KEY est requis pour le provider Anthropic")
            if self.llm_provider == "ollama" and not self.llm_base_url:
                raise ValueError("LLM_BASE_URL est requis pour le provider Ollama")

    def __post_init__(self):
        """Validation de la configuration"""
        if not self.elasticsearch_url:
            raise ValueError("ELASTICSEARCH_URL est requis")

        if self.analysis_interval < 60:
            raise ValueError("ANALYSIS_INTERVAL doit être au moins 60 secondes")

        if not (0 < self.anomaly_threshold < 1):
            raise ValueError("ANOMALY_THRESHOLD doit être entre 0 et 1")
