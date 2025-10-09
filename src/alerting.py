"""
Gestionnaire d'alertes pour l'agent SRE
"""

import asyncio
import logging
import json
import smtplib
from datetime import datetime, UTC
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Any
import aiohttp

from .config import Config
from .models import Alert

logger = logging.getLogger(__name__)


class AlertManager:
    """
    Gestionnaire d'alertes supportant multiple canaux de notification
    """

    def __init__(self, config: Config):
        self.config = config
        self.alert_history: List[Alert] = []
        self.rate_limits: Dict[str, datetime] = {}  # Pour éviter le spam d'alertes

    async def send_alert(self, alert: Alert):
        """Envoie une alerte via tous les canaux configurés"""
        try:
            # Vérifier le rate limiting
            if self._is_rate_limited(alert):
                logger.debug(f"Alerte rate-limitée: {alert.type}")
                return

            # Ajouter à l'historique
            self.alert_history.append(alert)

            # Garder seulement les 1000 dernières alertes
            if len(self.alert_history) > 1000:
                self.alert_history = self.alert_history[-1000:]

            logger.info(f"Envoi d'alerte: {alert.type} - {alert.severity} - {alert.message}")

            # Envoyer via tous les canaux configurés
            tasks = []

            if self.config.webhook_url:
                tasks.append(self._send_webhook(alert))

            if self.config.slack_webhook:
                tasks.append(self._send_slack(alert))

            if self.config.email_recipients:
                tasks.append(self._send_email(alert))

            # Exécuter tous les envois en parallèle
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            else:
                logger.warning("Aucun canal d'alerte configuré")

        except Exception as e:
            logger.error(f"Erreur lors de l'envoi d'alerte: {e}")

    def _is_rate_limited(self, alert: Alert) -> bool:
        """Vérifie si l'alerte est rate-limitée"""
        # Clé pour le rate limiting basée sur type + métadonnées principales
        rate_key = f"{alert.type}:{alert.metadata.get('pod_name', 'unknown')}"

        now = datetime.now(UTC)

        # Vérifier le dernier envoi
        if rate_key in self.rate_limits:
            last_sent = self.rate_limits[rate_key]
            time_diff = (now - last_sent).total_seconds()

            # Rate limit: max 1 alerte du même type par pod toutes les 5 minutes
            if time_diff < 300:
                return True

        # Mettre à jour le timestamp
        self.rate_limits[rate_key] = now

        # Nettoyer les anciens rate limits (plus de 1 heure)
        cutoff = now.timestamp() - 3600
        self.rate_limits = {k: v for k, v in self.rate_limits.items() if v.timestamp() > cutoff}

        return False

    async def _send_webhook(self, alert: Alert):
        """Envoie l'alerte via webhook générique"""
        try:
            payload = {
                "timestamp": alert.timestamp.isoformat(),
                "type": alert.type,
                "severity": alert.severity,
                "message": alert.message,
                "metadata": alert.metadata,
                "source": "efk-sre-agent",
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.config.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        logger.debug("Webhook envoyé avec succès")
                    else:
                        logger.warning(f"Échec webhook: {response.status}")

        except Exception as e:
            logger.error(f"Erreur webhook: {e}")

    async def _send_slack(self, alert: Alert):
        """Envoie l'alerte vers Slack"""
        try:
            # Déterminer la couleur selon la sévérité
            color_map = {
                "info": "#36a64f",  # Vert
                "warning": "#ff9500",  # Orange
                "critical": "#ff0000",  # Rouge
            }
            color = color_map.get(alert.severity, "#808080")

            # Construire le message Slack
            attachments: List[Dict[str, Any]] = [
                {
                    "color": color,
                    "title": f"🚨 Alerte {alert.severity.upper()}",
                    "text": alert.message,
                    "fields": [
                        {"title": "Type", "value": alert.type, "short": True},
                        {
                            "title": "Timestamp",
                            "value": alert.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC"),
                            "short": True,
                        },
                    ],
                    "footer": "EFK SRE Agent",
                    "ts": int(alert.timestamp.timestamp()),
                }
            ]

            # Ajouter les métadonnées importantes
            if alert.metadata:
                for key, value in alert.metadata.items():
                    if key in ["pod_name", "namespace", "cpu_usage", "memory_usage"]:
                        attachments[0]["fields"].append(
                            {
                                "title": key.replace("_", " ").title(),
                                "value": str(value),
                                "short": True,
                            }
                        )

            payload = {
                "text": f"Alerte EFK SRE - {alert.severity.upper()}",
                "attachments": attachments,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.config.slack_webhook,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        logger.debug("Slack envoyé avec succès")
                    else:
                        logger.warning(f"Échec Slack: {response.status}")

        except Exception as e:
            logger.error(f"Erreur Slack: {e}")

    async def _send_email(self, alert: Alert):
        """Envoie l'alerte par email"""
        try:
            if not all(
                [
                    self.config.email_smtp_server,
                    self.config.email_username,
                    self.config.email_password,
                ]
            ):
                logger.warning("Configuration email incomplète")
                return

            # Préparer le message
            msg = MIMEMultipart()
            msg["From"] = self.config.email_username
            msg["To"] = self.config.email_recipients
            msg[
                "Subject"
            ] = f"🚨 EFK SRE Alert - {alert.severity.upper()} - {alert.type}"

            # Corps du message
            body = f"""
Alerte générée par l'agent EFK SRE

Type: {alert.type}
Sévérité: {alert.severity.upper()}
Message: {alert.message}
Timestamp: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}

Métadonnées:
{json.dumps(alert.metadata, indent=2, default=str)}

---
Agent EFK SRE
            """

            msg.attach(MIMEText(body, "plain"))

            # Envoyer l'email
            await asyncio.get_event_loop().run_in_executor(None, self._send_email_sync, msg)

            logger.debug("Email envoyé avec succès")

        except Exception as e:
            logger.error(f"Erreur email: {e}")

    def _send_email_sync(self, msg):
        """Envoie l'email de manière synchrone"""
        server = smtplib.SMTP(self.config.email_smtp_server, self.config.email_smtp_port)
        server.starttls()
        server.login(self.config.email_username, self.config.email_password)
        server.send_message(msg)
        server.quit()

    def get_alert_stats(self) -> dict:
        """Retourne des statistiques sur les alertes"""
        if not self.alert_history:
            return {"total_alerts": 0, "by_severity": {}, "by_type": {}, "last_24h": 0}

        now = datetime.now(UTC)
        last_24h = [a for a in self.alert_history if (now - a.timestamp).total_seconds() < 86400]

        severity_counts: Dict[str, int] = {}
        type_counts: Dict[str, int] = {}

        for alert in self.alert_history:
            severity_counts[alert.severity] = severity_counts.get(alert.severity, 0) + 1
            type_counts[alert.type] = type_counts.get(alert.type, 0) + 1

        return {
            "total_alerts": len(self.alert_history),
            "by_severity": severity_counts,
            "by_type": type_counts,
            "last_24h": len(last_24h),
        }

    def get_recent_alerts(self, limit: int = 50) -> List[Alert]:
        """Retourne les alertes récentes"""
        return sorted(self.alert_history, key=lambda x: x.timestamp, reverse=True)[:limit]
