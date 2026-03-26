import pytest
from src.config import Config


class TestConfigDefaults:
    def test_default_values(self):
        config = Config(elasticsearch_url="http://localhost:9200")
        assert config.elasticsearch_url == "http://localhost:9200"
        assert config.elasticsearch_username == ""
        assert config.elasticsearch_password == ""
        assert config.elasticsearch_indices_metrics == "sre-metrics"
        assert config.elasticsearch_indices_logs == "sre-logs"
        assert config.elasticsearch_indices_anomalies == "sre-anomalies"
        assert config.agent_analysis_interval == 300
        assert config.agent_log_level == "INFO"
        assert config.collectors_prometheus_enabled is True
        assert config.collectors_prometheus_url == "http://prometheus-server:9090"
        assert config.collectors_metrics_server_enabled is True
        assert config.collectors_k8s_api_enabled is True
        assert config.collectors_k8s_api_watch_events is True
        assert config.thresholds_cpu_warning == 70.0
        assert config.thresholds_cpu_critical == 85.0
        assert config.thresholds_memory_warning == 70.0
        assert config.thresholds_memory_critical == 85.0
        assert config.thresholds_disk_warning == 80.0
        assert config.thresholds_disk_critical == 90.0
        assert config.ml_retrain_interval == 3600
        assert config.ml_window_size == 100
        assert config.ml_anomaly_threshold == 0.05
        assert config.intelligence_enabled is False
        assert config.intelligence_provider == ""
        assert config.intelligence_api_url == ""
        assert config.intelligence_api_key == ""
        assert config.intelligence_model == ""
        assert config.alerter_alertmanager_enabled is True
        assert config.alerter_alertmanager_url == "http://alertmanager:9093"
        assert config.alerter_fallback_webhook_enabled is False
        assert config.alerter_fallback_webhook_url == ""


class TestConfigValidation:
    def test_elasticsearch_url_required(self):
        with pytest.raises(ValueError):
            Config(elasticsearch_url="")

    def test_analysis_interval_minimum(self):
        with pytest.raises(ValueError):
            Config(
                elasticsearch_url="http://localhost:9200", agent_analysis_interval=30
            )

    def test_anomaly_threshold_range(self):
        with pytest.raises(ValueError):
            Config(elasticsearch_url="http://localhost:9200", ml_anomaly_threshold=1.5)

    def test_threshold_ordering_cpu(self):
        with pytest.raises(ValueError):
            Config(
                elasticsearch_url="http://localhost:9200",
                thresholds_cpu_warning=90.0,
                thresholds_cpu_critical=80.0,
            )

    def test_threshold_ordering_memory(self):
        with pytest.raises(ValueError):
            Config(
                elasticsearch_url="http://localhost:9200",
                thresholds_memory_warning=90.0,
                thresholds_memory_critical=80.0,
            )

    def test_threshold_ordering_disk(self):
        with pytest.raises(ValueError):
            Config(
                elasticsearch_url="http://localhost:9200",
                thresholds_disk_warning=95.0,
                thresholds_disk_critical=90.0,
            )
