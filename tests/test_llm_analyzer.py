"""
Tests pour l'analyseur LLM
"""

import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, UTC

from src.config import Config
from src.llm_analyzer import LLMAnalyzer
from src.models import Alert, LogEntry


@pytest.fixture
def config_llm_disabled():
    """Configuration avec LLM désactivé"""
    config = Config()
    config.llm_enabled = False
    return config


@pytest.fixture
def config_llm_openai():
    """Configuration avec LLM OpenAI activé"""
    config = Config()
    config.llm_enabled = True
    config.llm_provider = "openai"
    config.llm_api_key = "test-api-key"
    config.llm_model = "gpt-3.5-turbo"
    config.llm_max_tokens = 1000
    config.llm_temperature = 0.1
    return config


@pytest.fixture
def config_llm_ollama():
    """Configuration avec LLM Ollama activé"""
    config = Config()
    config.llm_enabled = True
    config.llm_provider = "ollama"
    config.llm_model = "llama2"
    config.llm_base_url = "http://localhost:11434"
    config.llm_max_tokens = 1000
    config.llm_temperature = 0.1
    return config


@pytest.fixture
def sample_alert():
    """Alerte d'exemple pour les tests"""
    return Alert(
        type="resource_usage",
        severity="critical",
        message="CPU usage critical: 95% on pod web-app-123",
        timestamp=datetime.now(UTC),
        metadata={
            "pod_name": "web-app-123",
            "namespace": "production",
            "cpu_percent": 95,
        },
    )


@pytest.fixture
def sample_logs():
    """Logs d'exemple pour les tests"""
    return [
        LogEntry(
            timestamp=datetime.now(UTC),
            pod_name="web-app-123",
            namespace="default",
            message="OutOfMemoryError: Java heap space",
            log_level="ERROR",
        ),
        LogEntry(
            timestamp=datetime.now(UTC),
            pod_name="web-app-123",
            namespace="default",
            message="Connection timeout to database",
            log_level="ERROR",
        ),
        LogEntry(
            timestamp=datetime.now(UTC),
            pod_name="api-service-456",
            namespace="default",
            message="HTTP 500 Internal Server Error",
            log_level="ERROR",
        ),
    ]


class TestLLMAnalyzer:
    """Tests pour la classe LLMAnalyzer"""

    def test_init_disabled(self, config_llm_disabled):
        """Test d'initialisation avec LLM désactivé"""
        analyzer = LLMAnalyzer(config_llm_disabled)

        assert not analyzer.enabled
        assert analyzer.provider == "openai"  # valeur par défaut

    def test_init_enabled_openai(self, config_llm_openai):
        """Test d'initialisation avec OpenAI"""
        analyzer = LLMAnalyzer(config_llm_openai)

        assert analyzer.enabled
        assert analyzer.provider == "openai"
        assert analyzer.api_key == "test-api-key"
        assert analyzer.model == "gpt-3.5-turbo"

    def test_init_enabled_ollama(self, config_llm_ollama):
        """Test d'initialisation avec Ollama"""
        analyzer = LLMAnalyzer(config_llm_ollama)

        assert analyzer.enabled
        assert analyzer.provider == "ollama"
        assert analyzer.base_url == "http://localhost:11434"
        assert analyzer.model == "llama2"

    @pytest.mark.asyncio
    async def test_enhance_alert_disabled(self, config_llm_disabled, sample_alert):
        """Test d'amélioration d'alerte avec LLM désactivé"""
        analyzer = LLMAnalyzer(config_llm_disabled)

        result = await analyzer.enhance_alert_interpretation(sample_alert)

        assert not result["enhanced"]
        assert result["original_message"] == sample_alert.message
        assert result["interpretation"] is None

    @pytest.mark.asyncio
    async def test_analyze_logs_disabled(self, config_llm_disabled, sample_logs):
        """Test d'analyse de logs avec LLM désactivé"""
        analyzer = LLMAnalyzer(config_llm_disabled)

        result = await analyzer.analyze_log_patterns(sample_logs)

        assert not result["enhanced"]
        assert result["patterns"] == []

    @pytest.mark.asyncio
    async def test_troubleshooting_disabled(self, config_llm_disabled, sample_alert):
        """Test de guide de dépannage avec LLM désactivé"""
        analyzer = LLMAnalyzer(config_llm_disabled)

        result = await analyzer.provide_troubleshooting_guidance(sample_alert)

        assert not result["enhanced"]
        assert "désactivé" in result["guidance"]

    def test_build_alert_prompt(self, config_llm_openai, sample_alert):
        """Test de construction du prompt pour alerte"""
        analyzer = LLMAnalyzer(config_llm_openai)

        prompt = analyzer._build_alert_prompt(sample_alert)

        assert "CPU usage critical" in prompt
        assert "web-app-123" in prompt
        assert "JSON" in prompt
        assert "interpretation" in prompt

    def test_build_logs_prompt(self, config_llm_openai, sample_logs):
        """Test de construction du prompt pour logs"""
        analyzer = LLMAnalyzer(config_llm_openai)

        prompt = analyzer._build_logs_prompt(sample_logs)

        assert "OutOfMemoryError" in prompt
        assert "patterns" in prompt
        assert "JSON" in prompt

    def test_parse_alert_response_valid(self, config_llm_openai):
        """Test de parsing d'une réponse LLM valide"""
        analyzer = LLMAnalyzer(config_llm_openai)

        response = """
        {
            "interpretation": "High CPU usage detected",
            "recommendations": ["Scale up", "Check code"],
            "severity_assessment": "HIGH"
        }
        """

        result = analyzer._parse_alert_response(response)

        assert result["interpretation"] == "High CPU usage detected"
        assert len(result["recommendations"]) == 2
        assert result["severity_assessment"] == "HIGH"

    def test_parse_alert_response_invalid(self, config_llm_openai):
        """Test de parsing d'une réponse LLM invalide"""
        analyzer = LLMAnalyzer(config_llm_openai)

        response = "Invalid JSON response"

        result = analyzer._parse_alert_response(response)

        assert "Erreur de parsing" in result["interpretation"]
        assert result["recommendations"] == []

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_call_openai_success(self, mock_post, config_llm_openai):
        """Test d'appel OpenAI réussi"""
        analyzer = LLMAnalyzer(config_llm_openai)

        # Mock de la réponse
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Test response"}}]
        }
        mock_post.return_value.__aenter__.return_value = mock_response

        result = await analyzer._call_openai("test prompt")

        assert result == "Test response"
        mock_post.assert_called_once()

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_call_openai_error(self, mock_post, config_llm_openai):
        """Test d'appel OpenAI avec erreur"""
        analyzer = LLMAnalyzer(config_llm_openai)

        # Mock d'une erreur
        mock_response = AsyncMock()
        mock_response.status = 401
        mock_response.text.return_value = "Unauthorized"
        mock_post.return_value.__aenter__.return_value = mock_response

        result = await analyzer._call_openai("test prompt")

        assert result is None

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.post")
    async def test_call_ollama_success(self, mock_post, config_llm_ollama):
        """Test d'appel Ollama réussi"""
        analyzer = LLMAnalyzer(config_llm_ollama)

        # Mock de la réponse
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {"response": "Test response from Ollama"}
        mock_post.return_value.__aenter__.return_value = mock_response

        result = await analyzer._call_ollama("test prompt")

        assert result == "Test response from Ollama"

    @pytest.mark.asyncio
    async def test_enhance_alert_with_error(self, config_llm_openai, sample_alert):
        """Test d'amélioration d'alerte avec erreur LLM"""
        analyzer = LLMAnalyzer(config_llm_openai)

        # Forcer une erreur en modifiant la méthode _call_llm
        async def mock_call_llm(prompt):
            raise Exception("API Error")

        analyzer._call_llm = mock_call_llm

        result = await analyzer.enhance_alert_interpretation(sample_alert)

        assert not result["enhanced"]
        assert result["original_message"] == sample_alert.message
        assert "error" in result


class TestLLMIntegration:
    """Tests d'intégration pour les fonctionnalités LLM"""

    @pytest.mark.asyncio
    async def test_full_workflow_disabled(
        self, config_llm_disabled, sample_alert, sample_logs
    ):
        """Test du workflow complet avec LLM désactivé"""
        analyzer = LLMAnalyzer(config_llm_disabled)

        # Test des trois fonctionnalités principales
        alert_result = await analyzer.enhance_alert_interpretation(sample_alert)
        logs_result = await analyzer.analyze_log_patterns(sample_logs)
        troubleshoot_result = await analyzer.provide_troubleshooting_guidance(
            sample_alert
        )

        # Toutes doivent retourner enhanced=False
        assert not alert_result["enhanced"]
        assert not logs_result["enhanced"]
        assert not troubleshoot_result["enhanced"]

    def test_prompt_construction_consistency(
        self, config_llm_openai, sample_alert, sample_logs
    ):
        """Test de cohérence dans la construction des prompts"""
        analyzer = LLMAnalyzer(config_llm_openai)

        # Construire différents types de prompts
        alert_prompt = analyzer._build_alert_prompt(sample_alert)
        logs_prompt = analyzer._build_logs_prompt(sample_logs)
        troubleshoot_prompt = analyzer._build_troubleshooting_prompt(sample_alert)

        # Vérifier que tous contiennent les instructions JSON
        for prompt in [alert_prompt, logs_prompt, troubleshoot_prompt]:
            assert "JSON" in prompt
            assert "{" in prompt and "}" in prompt

        # Vérifier le contenu spécifique
        assert sample_alert.message in alert_prompt
        assert "OutOfMemoryError" in logs_prompt
        assert sample_alert.type in troubleshoot_prompt


if __name__ == "__main__":
    pytest.main([__file__])
