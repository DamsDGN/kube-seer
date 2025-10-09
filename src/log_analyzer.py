"""
Analyseur de logs avec détection d'anomalies et classification des erreurs
"""

import logging
import re
import pickle
import os
from datetime import datetime, UTC
from typing import List, Dict, Set
from collections import Counter
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import DBSCAN
from sklearn.ensemble import RandomForestClassifier

from .config import Config
from .models import LogEntry, Alert

logger = logging.getLogger(__name__)


class LogAnalyzer:
    """
    Analyseur de logs utilisant NLP et ML pour la détection d'anomalies
    """

    def __init__(self, config: Config):
        self.config = config
        self.vectorizer = TfidfVectorizer(
            max_features=1000, stop_words="english", ngram_range=(1, 2)
        )
        self.clustering_model = DBSCAN(eps=0.5, min_samples=3)
        self.classifier = RandomForestClassifier(n_estimators=100, random_state=42)

        self.error_patterns = self._load_error_patterns()
        self.known_errors: Set[str] = set()
        self.is_trained = False

        # Chemins de sauvegarde
        self.vectorizer_path = "/tmp/log_vectorizer.pkl"
        self.classifier_path = "/tmp/log_classifier.pkl"
        self.patterns_path = "/tmp/error_patterns.pkl"

        self.load_models()

    def _load_error_patterns(self) -> Dict[str, List[str]]:
        """Charge les patterns d'erreurs prédéfinis"""
        return {
            "oom_killer": [
                r"killed process.*out of memory",
                r"memory: usage \d+kB, limit \d+kB",
                r"oom.*killed.*process",
            ],
            "disk_space": [
                r"no space left on device",
                r"disk.*full",
                r"filesystem.*full",
            ],
            "network_error": [
                r"connection.*refused",
                r"network.*unreachable",
                r"timeout.*connection",
                r"dns.*resolution.*failed",
            ],
            "authentication": [
                r"authentication.*failed",
                r"invalid.*credentials",
                r"unauthorized.*access",
                r"permission.*denied",
            ],
            "database_error": [
                r"connection.*database.*failed",
                r"sql.*error",
                r"database.*timeout",
                r"deadlock.*detected",
            ],
            "application_error": [
                r"null.*pointer.*exception",
                r"index.*out.*of.*bounds",
                r"class.*not.*found",
                r"method.*not.*found",
            ],
        }

    async def analyze(self, logs: List[LogEntry]) -> List[Alert]:
        """Analyse les logs et détecte les anomalies"""
        if not logs:
            return []

        alerts = []

        try:
            # Analyser avec les patterns prédéfinis
            pattern_alerts = self._analyze_patterns(logs)
            alerts.extend(pattern_alerts)

            # Analyser la fréquence des erreurs
            frequency_alerts = self._analyze_frequency(logs)
            alerts.extend(frequency_alerts)

            # Analyser avec ML si entraîné
            if self.is_trained:
                ml_alerts = await self._analyze_with_ml(logs)
                alerts.extend(ml_alerts)

            # Détecter les nouvelles erreurs
            new_error_alerts = self._detect_new_errors(logs)
            alerts.extend(new_error_alerts)

        except Exception as e:
            logger.error(f"Erreur lors de l'analyse des logs: {e}")
            alerts.append(
                Alert(
                    type="log_analysis_error",
                    severity="warning",
                    message=f"Erreur d'analyse des logs: {e}",
                    timestamp=datetime.now(UTC),
                )
            )

        return alerts

    def _analyze_patterns(self, logs: List[LogEntry]) -> List[Alert]:
        """Analyse basée sur des patterns d'erreurs connus"""
        alerts = []
        pattern_matches: Dict[str, List[LogEntry]] = {}

        for log in logs:
            message = log.message.lower()

            for error_type, patterns in self.error_patterns.items():
                for pattern in patterns:
                    if re.search(pattern, message, re.IGNORECASE):
                        if error_type not in pattern_matches:
                            pattern_matches[error_type] = []
                        pattern_matches[error_type].append(log)
                        break

        # Générer des alertes pour les patterns détectés
        for error_type, matched_logs in pattern_matches.items():
            if len(matched_logs) > 1:  # Plusieurs occurrences
                severity = "critical" if len(matched_logs) > 5 else "warning"

                # Grouper par pod
                pods = list(set([log.pod_name for log in matched_logs]))

                alerts.append(
                    Alert(
                        type="log_error",
                        severity=severity,
                        message=f"Erreur {error_type} détectée: {len(matched_logs)} occurrences "
                        f"sur {len(pods)} pod(s)",
                        timestamp=datetime.now(UTC),
                        metadata={
                            "error_type": error_type,
                            "occurrences": len(matched_logs),
                            "affected_pods": pods,
                            "first_occurrence": matched_logs[0].timestamp.isoformat(),
                            "last_occurrence": matched_logs[-1].timestamp.isoformat(),
                        },
                    )
                )

        return alerts

    def _analyze_frequency(self, logs: List[LogEntry]) -> List[Alert]:
        """Analyse la fréquence des erreurs par pod"""
        alerts = []

        # Compter les erreurs par pod et par minute
        error_counts = {}

        for log in logs:
            if log.log_level.upper() in ["ERROR", "CRITICAL", "FATAL"]:
                minute = log.timestamp.replace(second=0, microsecond=0)
                key = (log.pod_name, minute)

                if key not in error_counts:
                    error_counts[key] = 0
                error_counts[key] += 1

        # Détecter les pics d'erreurs
        for (pod_name, minute), count in error_counts.items():
            if count > 10:  # Plus de 10 erreurs par minute
                severity = "critical" if count > 50 else "warning"

                alerts.append(
                    Alert(
                        type="log_error",
                        severity=severity,
                        message=f"Pic d'erreurs détecté sur {pod_name}: {count} erreurs/minute",
                        timestamp=datetime.now(UTC),
                        metadata={
                            "pod_name": pod_name,
                            "error_count": count,
                            "time_window": minute.isoformat(),
                            "analysis_type": "frequency",
                        },
                    )
                )

        return alerts

    async def _analyze_with_ml(self, logs: List[LogEntry]) -> List[Alert]:
        """Analyse avec modèles ML"""
        alerts: List[Alert] = []

        try:
            # Préparer les données
            messages = [log.message for log in logs]

            if not messages:
                return alerts

            # Vectoriser les messages
            try:
                X = self.vectorizer.transform(messages)
            except Exception:
                # Le vectorizer n'est pas encore entraîné
                return alerts

            # Clustering pour détecter des groupes d'erreurs similaires
            clusters = self.clustering_model.fit_predict(X.toarray())

            # Analyser les clusters
            cluster_counts = Counter(clusters)

            for cluster_id, count in cluster_counts.items():
                if (
                    cluster_id != -1 and count > 5
                ):  # Ignorer le bruit (-1) et les petits clusters
                    cluster_logs = [
                        logs[i] for i, c in enumerate(clusters) if c == cluster_id
                    ]
                    sample_message = cluster_logs[0].message[:100]

                    alerts.append(
                        Alert(
                            type="log_error",
                            severity="warning",
                            message=f"Cluster d'erreurs similaires détecté: {count} occurrences "
                            f"(ex: {sample_message}...)",
                            timestamp=datetime.now(UTC),
                            metadata={
                                "cluster_id": int(cluster_id),
                                "cluster_size": count,
                                "sample_message": sample_message,
                                "analysis_type": "clustering",
                            },
                        )
                    )

        except Exception as e:
            logger.error(f"Erreur lors de l'analyse ML des logs: {e}")

        return alerts

    def _detect_new_errors(self, logs: List[LogEntry]) -> List[Alert]:
        """Détecte de nouveaux types d'erreurs"""
        alerts = []
        new_errors = set()

        for log in logs:
            if log.log_level.upper() in ["ERROR", "CRITICAL", "FATAL"]:
                # Extraire des mots-clés de l'erreur
                error_signature = self._extract_error_signature(log.message)

                if error_signature and error_signature not in self.known_errors:
                    new_errors.add(error_signature)
                    self.known_errors.add(error_signature)

        for error_signature in new_errors:
            alerts.append(
                Alert(
                    type="log_error",
                    severity="info",
                    message=f"Nouveau type d'erreur détecté: {error_signature}",
                    timestamp=datetime.now(UTC),
                    metadata={
                        "error_signature": error_signature,
                        "analysis_type": "new_error",
                    },
                )
            )

        return alerts

    def _extract_error_signature(self, message: str) -> str:
        """Extrait une signature d'erreur du message"""
        # Supprimer les éléments variables (dates, IDs, etc.)
        signature = re.sub(r"\d{4}-\d{2}-\d{2}", "DATE", message)
        signature = re.sub(r"\d{2}:\d{2}:\d{2}", "TIME", signature)
        signature = re.sub(
            r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",
            "UUID",
            signature,
        )
        signature = re.sub(r"\d+", "NUM", signature)
        signature = re.sub(r"[^\w\s]", " ", signature)

        # Garder seulement les mots importants
        words = signature.split()
        important_words = [
            w
            for w in words
            if len(w) > 3
            and w.lower() not in ["the", "and", "for", "are", "but", "not"]
        ]

        return " ".join(important_words[:5])  # Limiter à 5 mots

    async def update_model(self, logs: List[LogEntry]):
        """Met à jour les modèles ML avec de nouveaux logs"""
        if len(logs) < 50:  # Minimum de logs pour l'entraînement
            return

        try:
            logger.info("Mise à jour du modèle de logs")

            # Préparer les données d'entraînement
            messages = [log.message for log in logs]
            labels = [
                1 if log.log_level.upper() in ["ERROR", "CRITICAL", "FATAL"] else 0
                for log in logs
            ]

            if not messages:
                return

            # Entraîner le vectorizer
            X = self.vectorizer.fit_transform(messages)

            # Entraîner le classificateur si on a des labels variés
            if len(set(labels)) > 1:
                self.classifier.fit(X, labels)
                self.is_trained = True

            # Sauvegarder les modèles
            self.save_models()

            logger.info(f"Modèle de logs mis à jour avec {len(logs)} échantillons")

        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour du modèle de logs: {e}")

    def save_models(self):
        """Sauvegarde les modèles"""
        try:
            with open(self.vectorizer_path, "wb") as f:
                pickle.dump(self.vectorizer, f)

            with open(self.classifier_path, "wb") as f:
                pickle.dump(self.classifier, f)

            with open(self.patterns_path, "wb") as f:
                pickle.dump(self.known_errors, f)

        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde des modèles de logs: {e}")

    def load_models(self):
        """Charge les modèles sauvegardés"""
        try:
            if os.path.exists(self.vectorizer_path):
                with open(self.vectorizer_path, "rb") as f:
                    self.vectorizer = pickle.load(f)

            if os.path.exists(self.classifier_path):
                with open(self.classifier_path, "rb") as f:
                    self.classifier = pickle.load(f)
                self.is_trained = True

            if os.path.exists(self.patterns_path):
                with open(self.patterns_path, "rb") as f:
                    self.known_errors = pickle.load(f)

            logger.info("Modèles de logs chargés")

        except Exception as e:
            logger.error(f"Erreur lors du chargement des modèles de logs: {e}")
            self.is_trained = False
