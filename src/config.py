"""
Configuration de l'agent SRE
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    """Configuration de l'agent SRE"""
    
    # Elasticsearch
    elasticsearch_url: str = os.getenv("ELASTICSEARCH_URL", "http://elasticsearch:9200")
    elasticsearch_user: str = os.getenv("ELASTICSEARCH_USER", "elastic")
    elasticsearch_password: str = os.getenv("ELASTICSEARCH_PASSWORD", "")
    
    # Index Elasticsearch
    metrics_index: str = os.getenv("METRICS_INDEX", "metricbeat-*")
    logs_index: str = os.getenv("LOGS_INDEX", "fluentd-*")
    
    # Kubernetes
    k8s_in_cluster: bool = os.getenv("K8S_IN_CLUSTER", "true").lower() == "true"
    k8s_namespace: str = os.getenv("K8S_NAMESPACE", "default")
    
    # Analyse
    analysis_interval: int = int(os.getenv("ANALYSIS_INTERVAL", "300"))  # 5 minutes
    anomaly_threshold: float = float(os.getenv("ANOMALY_THRESHOLD", "0.05"))
    
    # Seuils d'alerte
    cpu_threshold_warning: float = float(os.getenv("CPU_THRESHOLD_WARNING", "70.0"))
    cpu_threshold_critical: float = float(os.getenv("CPU_THRESHOLD_CRITICAL", "85.0"))
    memory_threshold_warning: float = float(os.getenv("MEMORY_THRESHOLD_WARNING", "70.0"))
    memory_threshold_critical: float = float(os.getenv("MEMORY_THRESHOLD_CRITICAL", "85.0"))
    
    # Alerting
    webhook_url: Optional[str] = os.getenv("WEBHOOK_URL")
    slack_webhook: Optional[str] = os.getenv("SLACK_WEBHOOK")
    email_smtp_server: str = os.getenv("EMAIL_SMTP_SERVER", "")
    email_smtp_port: int = int(os.getenv("EMAIL_SMTP_PORT", "587"))
    email_username: str = os.getenv("EMAIL_USERNAME", "")
    email_password: str = os.getenv("EMAIL_PASSWORD", "")
    email_recipients: str = os.getenv("EMAIL_RECIPIENTS", "")
    
    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    
    # Modèles ML
    model_retrain_interval: int = int(os.getenv("MODEL_RETRAIN_INTERVAL", "3600"))  # 1 heure
    model_window_size: int = int(os.getenv("MODEL_WINDOW_SIZE", "100"))
    
    def __post_init__(self):
        """Validation de la configuration"""
        if not self.elasticsearch_url:
            raise ValueError("ELASTICSEARCH_URL est requis")
        
        if self.analysis_interval < 60:
            raise ValueError("ANALYSIS_INTERVAL doit être au moins 60 secondes")
        
        if not (0 < self.anomaly_threshold < 1):
            raise ValueError("ANOMALY_THRESHOLD doit être entre 0 et 1")