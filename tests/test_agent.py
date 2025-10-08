"""
Tests unitaires pour l'agent SRE
"""

import pytest
import asyncio
import sys
import os
from datetime import datetime, UTC, timedelta
from unittest.mock import Mock, AsyncMock, patch

# Ajouter le répertoire src au path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from config import Config
from models import Metric, LogEntry, Alert
from metrics_analyzer import MetricsAnalyzer
from log_analyzer import LogAnalyzer
from alerting import AlertManager
from agent import SREAgent


@pytest.fixture
def config():
    """Configuration de test"""
    return Config()


@pytest.fixture
def sample_metrics():
    """Données de test pour les métriques"""
    return [
        Metric(
            pod_name="test-pod-1",
            cpu_usage=50000000,  # 50m cores
            memory_usage=100 * 1024 * 1024,  # 100MB
            cpu_peak=80000000,
            memory_peak=120 * 1024 * 1024,
            timestamp=datetime.now(UTC)
        ),
        Metric(
            pod_name="test-pod-2",
            cpu_usage=900000000,  # 900m cores (élevé)
            memory_usage=800 * 1024 * 1024,  # 800MB (élevé)
            cpu_peak=950000000,
            memory_peak=850 * 1024 * 1024,
            timestamp=datetime.now(UTC)
        )
    ]


@pytest.fixture
def sample_logs():
    """Données de test pour les logs"""
    return [
        LogEntry(
            pod_name="test-pod-1",
            namespace="default",
            log_level="INFO",
            message="Application started successfully",
            timestamp=datetime.now(UTC)
        ),
        LogEntry(
            pod_name="test-pod-2",
            namespace="default",
            log_level="ERROR",
            message="Connection to database failed: timeout",
            timestamp=datetime.now(UTC)
        ),
        LogEntry(
            pod_name="test-pod-2",
            namespace="default",
            log_level="CRITICAL",
            message="Out of memory: killed process",
            timestamp=datetime.now(UTC)
        )
    ]


class TestConfig:
    """Tests pour la configuration"""
    
    def test_config_defaults(self):
        """Test des valeurs par défaut de la configuration"""
        config = Config()
        assert config.analysis_interval == 300
        assert config.cpu_threshold_warning == 70.0
        assert config.anomaly_threshold == 0.05
    
    def test_config_validation(self):
        """Test de la validation de la configuration"""
        # Test avec un interval trop bas
        os.environ['ANALYSIS_INTERVAL'] = '30'
        with pytest.raises(ValueError, match="ANALYSIS_INTERVAL doit être au moins 60"):
            Config()
        
        # Nettoyer l'environnement pour les autres tests
        if 'ANALYSIS_INTERVAL' in os.environ:
            del os.environ['ANALYSIS_INTERVAL']


class TestMetricsAnalyzer:
    """Tests pour l'analyseur de métriques"""
    
    def test_extract_features(self, config, sample_metrics):
        """Test d'extraction des features"""
        analyzer = MetricsAnalyzer(config)
        df = analyzer.extract_features(sample_metrics)
        
        assert len(df) == 2
        assert 'cpu_usage' in df.columns
        assert 'memory_usage' in df.columns
        assert 'hour_of_day' in df.columns
    
    @pytest.mark.asyncio
    async def test_analyze_thresholds(self, config, sample_metrics):
        """Test de l'analyse par seuils"""
        analyzer = MetricsAnalyzer(config)
        alerts = await analyzer.analyze(sample_metrics)
        
        # Doit détecter des alertes CPU/mémoire élevées pour test-pod-2
        assert len(alerts) > 0
        
        cpu_alerts = [a for a in alerts if a.type == "cpu_anomaly"]
        memory_alerts = [a for a in alerts if a.type == "memory_anomaly"]
        
        assert len(cpu_alerts) > 0 or len(memory_alerts) > 0
    
    def test_prepare_features(self, config, sample_metrics):
        """Test de préparation des features"""
        analyzer = MetricsAnalyzer(config)
        df = analyzer.extract_features(sample_metrics)
        features = analyzer.prepare_features(df)
        
        assert features.shape[0] == 2
        assert features.shape[1] == len(analyzer.feature_columns)


class TestLogAnalyzer:
    """Tests pour l'analyseur de logs"""
    
    def test_load_error_patterns(self, config):
        """Test du chargement des patterns d'erreurs"""
        analyzer = LogAnalyzer(config)
        patterns = analyzer.error_patterns
        
        assert 'oom_killer' in patterns
        assert 'database_error' in patterns
        assert len(patterns['oom_killer']) > 0
    
    @pytest.mark.asyncio
    async def test_analyze_patterns(self, config, sample_logs):
        """Test de l'analyse par patterns"""
        analyzer = LogAnalyzer(config)
        alerts = await analyzer.analyze(sample_logs)
        
        # Doit détecter l'erreur OOM
        oom_alerts = [a for a in alerts if 'oom' in a.message.lower() or 'memory' in a.message.lower()]
        assert len(oom_alerts) > 0
    
    def test_extract_error_signature(self, config):
        """Test d'extraction de signature d'erreur"""
        analyzer = LogAnalyzer(config)
        
        message = "2023-10-08 12:34:56 ERROR: Connection failed to 192.168.1.100:5432"
        signature = analyzer._extract_error_signature(message)
        
        assert 'ERROR' in signature
        assert 'Connection' in signature
        assert '192.168.1.100' not in signature  # IPs supprimées


class TestAlertManager:
    """Tests pour le gestionnaire d'alertes"""
    
    def test_rate_limiting(self, config):
        """Test du rate limiting"""
        manager = AlertManager(config)
        
        alert = Alert(
            type="test_alert",
            severity="warning",
            message="Test message",
            timestamp=datetime.now(UTC),
            metadata={'pod_name': 'test-pod'}
        )
        
        # Premier appel - pas de rate limit
        assert not manager._is_rate_limited(alert)
        
        # Deuxième appel immédiat - rate limité
        assert manager._is_rate_limited(alert)
    
    @pytest.mark.asyncio
    async def test_send_alert_without_channels(self, config):
        """Test d'envoi d'alerte sans canaux configurés"""
        manager = AlertManager(config)
        
        alert = Alert(
            type="test_alert",
            severity="warning",
            message="Test message",
            timestamp=datetime.now(UTC)
        )
        
        # Ne doit pas lever d'exception
        await manager.send_alert(alert)
        
        # L'alerte doit être dans l'historique
        assert len(manager.alert_history) == 1
    
    def test_alert_stats(self, config):
        """Test des statistiques d'alertes"""
        manager = AlertManager(config)
        
        # Ajouter quelques alertes
        for i in range(5):
            alert = Alert(
                type="test_alert",
                severity="warning" if i < 3 else "critical",
                message=f"Test message {i}",
                timestamp=datetime.now(UTC)
            )
            manager.alert_history.append(alert)
        
        stats = manager.get_alert_stats()
        
        assert stats['total_alerts'] == 5
        assert stats['by_severity']['warning'] == 3
        assert stats['by_severity']['critical'] == 2


class TestSREAgent:
    """Tests pour l'agent SRE principal"""
    
    @pytest.mark.asyncio
    async def test_agent_initialization(self, config):
        """Test d'initialisation de l'agent"""
        with patch('src.agent.Elasticsearch') as mock_es, \
             patch('src.agent.config.load_incluster_config'), \
             patch('src.agent.client.CoreV1Api'):
            
            mock_es.return_value.ping.return_value = True
            
            agent = SREAgent(config)
            await agent.initialize()
            
            assert agent.es_client is not None
            assert agent.k8s_client is not None
    
    @pytest.mark.asyncio
    async def test_correlate_anomalies(self, config):
        """Test de corrélation des anomalies"""
        agent = SREAgent(config)
        
        metric_alerts = [
            Alert(
                type="cpu_anomaly",
                severity="warning",
                message="CPU élevé",
                timestamp=datetime.now(UTC),
                metadata={'pod_name': 'test-pod-1'}
            )
        ]
        
        log_alerts = [
            Alert(
                type="log_error",
                severity="critical",
                message="Erreur application",
                timestamp=datetime.now(UTC),
                metadata={'pod_name': 'test-pod-1'}
            )
        ]
        
        correlated = await agent.correlate_anomalies(metric_alerts, log_alerts)
        
        # Doit détecter une corrélation
        assert len(correlated) > 0
        correlated_alert = next((a for a in correlated if a.type == "correlated_issue"), None)
        assert correlated_alert is not None
        assert correlated_alert.severity == "critical"


@pytest.mark.asyncio
async def test_integration_analysis_cycle(config):
    """Test d'intégration du cycle d'analyse complet"""
    with patch('src.agent.Elasticsearch') as mock_es, \
         patch('src.agent.config.load_incluster_config'), \
         patch('src.agent.client.CoreV1Api') as mock_k8s:
        
        # Configuration des mocks
        mock_es.return_value.ping.return_value = True
        mock_es.return_value.search.return_value = {
            'aggregations': {'pods': {'buckets': []}},
            'hits': {'hits': []}
        }
        
        agent = SREAgent(config)
        await agent.initialize()
        
        # Simuler un cycle d'analyse
        with patch.object(agent, 'collect_metrics') as mock_collect_metrics, \
             patch.object(agent, 'collect_logs') as mock_collect_logs:
            
            mock_collect_metrics.return_value = []
            mock_collect_logs.return_value = []
            
            # Ne doit pas lever d'exception
            await agent.run_analysis_cycle()


if __name__ == "__main__":
    pytest.main([__file__])