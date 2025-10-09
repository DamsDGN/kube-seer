"""
Analyseur LLM pour l'amélioration de l'interprétation des événements
"""

import json
import logging
from typing import List, Dict, Any, Optional
import aiohttp

from .config import Config
from .models import Alert, LogEntry, Metric
try:
    import aiohttp
except ImportError:
    aiohttp = None
from .models import Alert, LogEntry, Metric

logger = logging.getLogger(__name__)


class LLMAnalyzer:
    """
    Analyseur utilisant un LLM pour améliorer l'interprétation des événements
    """

    def __init__(self, config: Config):
        self.config = config
        self.enabled = config.llm_enabled
        self.provider = config.llm_provider
        self.api_key = config.llm_api_key
        self.model = config.llm_model
        self.base_url = config.llm_base_url
        self.max_tokens = config.llm_max_tokens
        self.temperature = config.llm_temperature

        if self.enabled:
            logger.info(f"LLM Analyzer initialisé avec {self.provider} ({self.model})")
        else:
            logger.info("LLM Analyzer désactivé")

    async def enhance_alert_interpretation(
        self, alert: Alert, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Améliore l'interprétation d'une alerte avec le LLM

        Args:
            alert: L'alerte à analyser
            context: Contexte additionnel (métriques, logs récents, etc.)

        Returns:
            Dictionnaire avec l'analyse améliorée
        """
        if not self.enabled:
            return {
                "enhanced": False,
                "original_message": alert.message,
                "interpretation": None,
                "recommendations": [],
                "severity_assessment": alert.severity,
            }

        try:
            prompt = self._build_alert_prompt(alert, context)
            response = await self._call_llm(prompt)

            if response:
                analysis = self._parse_alert_response(response)
                analysis["enhanced"] = True
                analysis["original_message"] = alert.message
                return analysis

        except Exception as e:
            logger.error(f"Erreur lors de l'analyse LLM de l'alerte: {e}")

        # Retour par défaut en cas d'erreur
        return {
            "enhanced": False,
            "original_message": alert.message,
            "interpretation": None,
            "recommendations": [],
            "severity_assessment": alert.severity,
            "error": "Analyse LLM indisponible",
        }

    async def analyze_log_patterns(
        self, logs: List[LogEntry], limit: int = 10
    ) -> Dict[str, Any]:
        """
        Analyse des patterns dans les logs avec le LLM

        Args:
            logs: Liste des entrées de logs
            limit: Nombre maximum de logs à analyser

        Returns:
            Analyse des patterns détectés
        """
        if not self.enabled or not logs:
            return {
                "enhanced": False,
                "patterns": [],
                "summary": "Analyse LLM désactivée",
            }

        try:
            # Limiter le nombre de logs pour éviter de dépasser les limites du LLM
            sample_logs = logs[:limit]
            prompt = self._build_logs_prompt(sample_logs)
            response = await self._call_llm(prompt)

            if response:
                analysis = self._parse_logs_response(response)
                analysis["enhanced"] = True
                analysis["analyzed_count"] = len(sample_logs)
                analysis["total_count"] = len(logs)
                return analysis

        except Exception as e:
            logger.error(f"Erreur lors de l'analyse LLM des logs: {e}")

        return {
            "enhanced": False,
            "patterns": [],
            "summary": "Erreur lors de l'analyse LLM",
        }

    async def provide_troubleshooting_guidance(
        self,
        alert: Alert,
        recent_metrics: Optional[List[Metric]] = None,
        recent_logs: Optional[List[LogEntry]] = None,
    ) -> Dict[str, Any]:
        """
        Fournit des conseils de dépannage basés sur l'alerte et le contexte

        Args:
            alert: L'alerte principale
            recent_metrics: Métriques récentes
            recent_logs: Logs récents

        Returns:
            Guide de dépannage structuré
        """
        if not self.enabled:
            return {"enhanced": False, "guidance": "Guide de dépannage LLM désactivé"}

        try:
            prompt = self._build_troubleshooting_prompt(
                alert, recent_metrics, recent_logs
            )
            response = await self._call_llm(prompt)

            if response:
                guidance = self._parse_troubleshooting_response(response)
                guidance["enhanced"] = True
                return guidance

        except Exception as e:
            logger.error(f"Erreur lors de la génération du guide de dépannage: {e}")

        return {
            "enhanced": False,
            "guidance": "Erreur lors de la génération du guide de dépannage",
        }

    def _build_alert_prompt(
        self, alert: Alert, context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Construit le prompt pour l'analyse d'alerte"""
        context_info = ""
        if context:
            if "pod_name" in context:
                context_info += f"Pod: {context['pod_name']}\n"
            if "namespace" in context:
                context_info += f"Namespace: {context['namespace']}\n"
            if "recent_cpu" in context:
                context_info += f"CPU récent: {context['recent_cpu']}%\n"
            if "recent_memory" in context:
                context_info += f"Mémoire récente: {context['recent_memory']}%\n"

        return f"""Tu es un expert SRE (Site Reliability Engineer) spécialisé dans \
l'analyse d'incidents Kubernetes.

Analyse cette alerte et fournis une interprétation détaillée :

**Alerte:**
- Type: {alert.type}
- Sévérité: {alert.severity}
- Message: {alert.message}
- Timestamp: {alert.timestamp}

**Contexte:**
{context_info if context_info else "Aucun contexte additionnel"}

**Métadonnées:**
{json.dumps(alert.metadata, indent=2) if alert.metadata else "Aucune"}

Réponds UNIQUEMENT en JSON avec cette structure exacte :
{{
    "interpretation": "Explication claire et concise de ce que signifie cette alerte",
    "root_cause": "Cause racine probable du problème",
    "impact": "Impact potentiel sur le système/utilisateurs",
    "urgency": "LOW|MEDIUM|HIGH|CRITICAL",
    "recommendations": [
        "Action immédiate 1",
        "Action immédiate 2",
        "Action de suivi 1"
    ],
    "investigation_steps": [
        "Étape de diagnostic 1",
        "Étape de diagnostic 2"
    ],
    "related_components": ["composant1", "composant2"]
}}"""

    def _build_logs_prompt(self, logs: List[LogEntry]) -> str:
        """Construit le prompt pour l'analyse des logs"""
        logs_text = "\n".join(
            [
                f"[{log.timestamp}] {log.pod_name}: {log.message}"
                for log in logs[:10]  # Limiter à 10 logs pour la taille du prompt
            ]
        )

        return f"""Tu es un expert SRE analysant des logs Kubernetes pour identifier \
des patterns et anomalies.

Analyse ces logs récents et identifie les patterns significatifs :

**Logs:**
```
{logs_text}
```

Réponds UNIQUEMENT en JSON avec cette structure exacte :
{{
    "patterns": [
        {{
            "type": "error|warning|info",
            "description": "Description du pattern",
            "frequency": "Fréquence observée",
            "severity": "LOW|MEDIUM|HIGH",
            "affected_pods": ["pod1", "pod2"]
        }}
    ],
    "summary": "Résumé des observations principales",
    "anomalies": [
        "Anomalie 1",
        "Anomalie 2"
    ],
    "trends": "Tendances observées dans les logs"
}}"""

    def _build_troubleshooting_prompt(
        self,
        alert: Alert,
        recent_metrics: Optional[List[Metric]] = None,
        recent_logs: Optional[List[LogEntry]] = None,
    ) -> str:
        """Construit le prompt pour le guide de dépannage"""
        metrics_info = ""
        if recent_metrics:
            metrics_info = (
                f"Métriques récentes: {len(recent_metrics)} entrées disponibles"
            )

        logs_info = ""
        if recent_logs:
            logs_info = (
                f"Logs récents: {len(recent_logs)} entrées, derniers messages:\n"
            )
            logs_info += "\n".join(
                [
                    log.message[:100] + "..." if len(log.message) > 100 else log.message
                    for log in recent_logs[:3]
                ]
            )

        return f"""Tu es un expert SRE créant un guide de dépannage pour une alerte système.

**Alerte à résoudre:**
- Type: {alert.type}
- Sévérité: {alert.severity}
- Message: {alert.message}

**Contexte disponible:**
{metrics_info}
{logs_info}

Crée un guide de dépannage structuré et actionnable.

Réponds UNIQUEMENT en JSON avec cette structure exacte :
{{
    "immediate_actions": [
        "Action immédiate 1",
        "Action immédiate 2"
    ],
    "diagnostic_commands": [
        {{
            "command": "kubectl get pods -n namespace",
            "purpose": "Vérifier l'état des pods"
        }}
    ],
    "common_solutions": [
        {{
            "problem": "Description du problème courant",
            "solution": "Solution recommandée"
        }}
    ],
    "escalation_criteria": [
        "Critère d'escalade 1",
        "Critère d'escalade 2"
    ],
    "prevention_tips": [
        "Conseil de prévention 1",
        "Conseil de prévention 2"
    ]
}}"""

    async def _call_llm(self, prompt: str) -> Optional[str]:
        """Appelle le LLM configuré"""
        try:
            if self.provider == "openai":
                return await self._call_openai(prompt)
            elif self.provider == "anthropic":
                return await self._call_anthropic(prompt)
            elif self.provider == "ollama":
                return await self._call_ollama(prompt)
            else:
                logger.error(f"Provider LLM non supporté: {self.provider}")
                return None

        except Exception as e:
            logger.error(f"Erreur lors de l'appel LLM: {e}")
            return None

    async def _call_openai(self, prompt: str) -> Optional[str]:
        """Appelle l'API OpenAI"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        data = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "Tu es un expert SRE. Réponds toujours en JSON valide.",
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return result["choices"][0]["message"]["content"]
                else:
                    logger.error(
                        f"Erreur OpenAI: {response.status} - {await response.text()}"
                    )
                    return None

    async def _call_anthropic(self, prompt: str) -> Optional[str]:
        """Appelle l'API Anthropic Claude"""
        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }

        data = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=data,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return result["content"][0]["text"]
                else:
                    logger.error(
                        f"Erreur Anthropic: {response.status} - {await response.text()}"
                    )
                    return None

    async def _call_ollama(self, prompt: str) -> Optional[str]:
        """Appelle une instance Ollama locale"""
        data = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/generate",
                json=data,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return result["response"]
                else:
                    logger.error(
                        f"Erreur Ollama: {response.status} - {await response.text()}"
                    )
                    return None

    def _parse_alert_response(self, response: str) -> Dict[str, Any]:
        """Parse la réponse LLM pour une analyse d'alerte"""
        try:
            # Extraire le JSON de la réponse si elle contient du texte supplémentaire
            start = response.find("{")
            end = response.rfind("}") + 1
            if start != -1 and end != 0:
                json_str = response[start:end]
                return json.loads(json_str)
            else:
                return json.loads(response)
        except json.JSONDecodeError as e:
            logger.error(f"Erreur de parsing JSON pour l'alerte: {e}")
            return {
                "interpretation": "Erreur de parsing de la réponse LLM",
                "recommendations": [],
                "severity_assessment": "UNKNOWN",
            }

    def _parse_logs_response(self, response: str) -> Dict[str, Any]:
        """Parse la réponse LLM pour une analyse de logs"""
        try:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start != -1 and end != 0:
                json_str = response[start:end]
                return json.loads(json_str)
            else:
                return json.loads(response)
        except json.JSONDecodeError as e:
            logger.error(f"Erreur de parsing JSON pour les logs: {e}")
            return {"patterns": [], "summary": "Erreur de parsing de la réponse LLM"}

    def _parse_troubleshooting_response(self, response: str) -> Dict[str, Any]:
        """Parse la réponse LLM pour un guide de dépannage"""
        try:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start != -1 and end != 0:
                json_str = response[start:end]
                return json.loads(json_str)
            else:
                return json.loads(response)
        except json.JSONDecodeError as e:
            logger.error(f"Erreur de parsing JSON pour le dépannage: {e}")
            return {
                "immediate_actions": [],
                "guidance": "Erreur de parsing de la réponse LLM",
            }
