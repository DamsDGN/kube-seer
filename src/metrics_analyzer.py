"""
Analyseur de métriques avec détection d'anomalies par ML
"""

import logging
import pickle
import os
from datetime import datetime, UTC
from typing import List

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from .config import Config
from .models import Metric, Alert

logger = logging.getLogger(__name__)


class MetricsAnalyzer:
    """
    Analyseur de métriques utilisant l'Isolation Forest pour la détection d'anomalies
    """

    def __init__(self, config: Config):
        self.config = config
        self.model = IsolationForest(
            contamination=config.anomaly_threshold, random_state=42, n_estimators=100
        )
        self.scaler = StandardScaler()
        self.is_trained = False
        self.feature_columns = [
            "cpu_usage",
            "memory_usage",
            "cpu_peak",
            "memory_peak",
            "cpu_trend",
            "memory_trend",
            "hour_of_day",
            "day_of_week",
        ]
        self.model_path = "/tmp/metrics_model.pkl"
        self.scaler_path = "/tmp/metrics_scaler.pkl"
        self.load_model()

    def extract_features(self, metrics: List[Metric]) -> pd.DataFrame:
        """Extrait les features des métriques pour le ML"""
        if not metrics:
            return pd.DataFrame()

        # Convertir en DataFrame
        data = []
        for metric in metrics:
            data.append(
                {
                    "pod_name": metric.pod_name,
                    "cpu_usage": metric.cpu_usage or 0,
                    "memory_usage": metric.memory_usage or 0,
                    "cpu_peak": metric.cpu_peak or 0,
                    "memory_peak": metric.memory_peak or 0,
                    "timestamp": metric.timestamp,
                    "hour_of_day": metric.timestamp.hour,
                    "day_of_week": metric.timestamp.weekday(),
                }
            )

        df = pd.DataFrame(data)

        if len(df) < 2:
            # Pas assez de données pour calculer les tendances
            df["cpu_trend"] = 0
            df["memory_trend"] = 0
        else:
            # Calculer les tendances (différence avec la valeur précédente)
            df = df.sort_values("timestamp")
            df["cpu_trend"] = df["cpu_usage"].diff().fillna(0)
            df["memory_trend"] = df["memory_usage"].diff().fillna(0)

        return df

    def prepare_features(self, df: pd.DataFrame) -> np.ndarray:
        """Prépare les features pour le modèle ML"""
        if df.empty:
            return np.array([])

        # Sélectionner les colonnes de features
        feature_df = df[self.feature_columns].copy()

        # Gérer les valeurs manquantes
        feature_df = feature_df.fillna(0)

        # Gérer les valeurs infinies
        feature_df = feature_df.replace([np.inf, -np.inf], 0)

        return feature_df.values

    async def analyze(self, metrics: List[Metric]) -> List[Alert]:
        """Analyse les métriques et détecte les anomalies"""
        if not metrics:
            return []

        alerts = []

        try:
            # Extraire les features
            df = self.extract_features(metrics)
            if df.empty:
                return []

            # Préparer les features pour le ML
            features = self.prepare_features(df)
            if features.size == 0:
                return []

            # Analyser avec les seuils classiques
            threshold_alerts = self._analyze_thresholds(df)
            alerts.extend(threshold_alerts)

            # Analyser avec ML si le modèle est entraîné
            if self.is_trained and len(features) > 0:
                ml_alerts = await self._analyze_with_ml(df, features)
                alerts.extend(ml_alerts)

        except Exception as e:
            logger.error(f"Erreur lors de l'analyse des métriques: {e}")
            alerts.append(
                Alert(
                    type="analysis_error",
                    severity="warning",
                    message=f"Erreur d'analyse des métriques: {e}",
                    timestamp=datetime.now(UTC),
                )
            )

        return alerts

    def _analyze_thresholds(self, df: pd.DataFrame) -> List[Alert]:
        """Analyse basée sur des seuils statiques"""
        alerts = []

        for _, row in df.iterrows():
            pod_name = row["pod_name"]
            cpu_usage = row["cpu_usage"]
            memory_usage = row["memory_usage"]

            # Convertir en pourcentage (supposant que les valeurs sont en nanocores/bytes)
            cpu_percent = (cpu_usage / 1000000000) * 100 if cpu_usage else 0
            memory_percent = (memory_usage / (1024**3)) * 100 if memory_usage else 0

            # Alertes CPU
            if cpu_percent > self.config.cpu_threshold_critical:
                alerts.append(
                    Alert(
                        type="cpu_anomaly",
                        severity="critical",
                        message=f"CPU critique sur {pod_name}: {cpu_percent:.1f}%",
                        timestamp=datetime.now(UTC),
                        metadata={
                            "pod_name": pod_name,
                            "cpu_usage": cpu_percent,
                            "threshold": self.config.cpu_threshold_critical,
                            "metric_type": "cpu",
                        },
                    )
                )
            elif cpu_percent > self.config.cpu_threshold_warning:
                alerts.append(
                    Alert(
                        type="cpu_anomaly",
                        severity="warning",
                        message=f"CPU élevé sur {pod_name}: {cpu_percent:.1f}%",
                        timestamp=datetime.now(UTC),
                        metadata={
                            "pod_name": pod_name,
                            "cpu_usage": cpu_percent,
                            "threshold": self.config.cpu_threshold_warning,
                            "metric_type": "cpu",
                        },
                    )
                )

            # Alertes mémoire
            if memory_percent > self.config.memory_threshold_critical:
                alerts.append(
                    Alert(
                        type="memory_anomaly",
                        severity="critical",
                        message=f"Mémoire critique sur {pod_name}: {memory_percent:.1f}%",
                        timestamp=datetime.now(UTC),
                        metadata={
                            "pod_name": pod_name,
                            "memory_usage": memory_percent,
                            "threshold": self.config.memory_threshold_critical,
                            "metric_type": "memory",
                        },
                    )
                )
            elif memory_percent > self.config.memory_threshold_warning:
                alerts.append(
                    Alert(
                        type="memory_anomaly",
                        severity="warning",
                        message=f"Mémoire élevée sur {pod_name}: {memory_percent:.1f}%",
                        timestamp=datetime.now(UTC),
                        metadata={
                            "pod_name": pod_name,
                            "memory_usage": memory_percent,
                            "threshold": self.config.memory_threshold_warning,
                            "metric_type": "memory",
                        },
                    )
                )

        return alerts

    async def _analyze_with_ml(self, df: pd.DataFrame, features: np.ndarray) -> List[Alert]:
        """Analyse avec le modèle ML"""
        alerts = []

        try:
            # Normaliser les features
            features_scaled = self.scaler.transform(features)

            # Prédiction des anomalies
            predictions = self.model.predict(features_scaled)
            anomaly_scores = self.model.decision_function(features_scaled)

            # Générer les alertes pour les anomalies détectées
            for i, (prediction, score) in enumerate(zip(predictions, anomaly_scores)):
                if prediction == -1:  # Anomalie détectée
                    row = df.iloc[i]

                    alerts.append(
                        Alert(
                            type="ml_anomaly",
                            severity="warning" if score > -0.2 else "critical",
                            message=f"Anomalie ML détectée sur {row['pod_name']} "
                            f"(score: {score:.3f})",
                            timestamp=datetime.now(UTC),
                            metadata={
                                "pod_name": row["pod_name"],
                                "anomaly_score": float(score),
                                "cpu_usage": float(row["cpu_usage"]),
                                "memory_usage": float(row["memory_usage"]),
                                "analysis_type": "ml",
                            },
                        )
                    )

        except Exception as e:
            logger.error(f"Erreur lors de l'analyse ML: {e}")

        return alerts

    async def update_model(self, metrics: List[Metric]):
        """Met à jour le modèle ML avec de nouvelles données"""
        if len(metrics) < self.config.model_window_size:
            return

        try:
            logger.info("Mise à jour du modèle de métriques")

            # Extraire les features
            df = self.extract_features(metrics)
            features = self.prepare_features(df)

            if len(features) < 10:  # Minimum de données pour l'entraînement
                return

            # Entraîner le modèle
            self.scaler.fit(features)
            features_scaled = self.scaler.transform(features)

            self.model.fit(features_scaled)
            self.is_trained = True

            # Sauvegarder le modèle
            self.save_model()

            logger.info(f"Modèle mis à jour avec {len(features)} échantillons")

        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour du modèle: {e}")

    def save_model(self):
        """Sauvegarde le modèle et le scaler"""
        try:
            with open(self.model_path, "wb") as f:
                pickle.dump(self.model, f)

            with open(self.scaler_path, "wb") as f:
                pickle.dump(self.scaler, f)

        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde du modèle: {e}")

    def load_model(self):
        """Charge le modèle et le scaler"""
        try:
            if os.path.exists(self.model_path) and os.path.exists(self.scaler_path):
                with open(self.model_path, "rb") as f:
                    self.model = pickle.load(f)

                with open(self.scaler_path, "rb") as f:
                    self.scaler = pickle.load(f)

                self.is_trained = True
                logger.info("Modèle chargé depuis le disque")

        except Exception as e:
            logger.error(f"Erreur lors du chargement du modèle: {e}")
            self.is_trained = False
