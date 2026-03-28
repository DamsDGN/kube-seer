# kube-seer

[![CI/CD Pipeline](https://github.com/DamsDGN/kube-seer/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/DamsDGN/kube-seer/actions/workflows/ci-cd.yml)
[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc-sa/4.0/)

Agent SRE intelligent pour Kubernetes — collecte des métriques, détecte les anomalies, corrèle les incidents et prédit les saturations de ressources avant qu'elles surviennent.

## Fonctionnalités

- **Collecte multi-sources** : Prometheus, Kubernetes Metrics Server, K8s API (nodes, pods, events, PVC, HPA, NetworkPolicy, ResourceQuota, Ingress)
- **Détection d'anomalies** : Analyse statistique (Z-score, IQR) sur CPU, mémoire, disque
- **Corrélation d'incidents** : Regroupe les anomalies liées en incidents cohérents
- **Prédiction de saturation** : Régression linéaire avec horizon configurable — prédit quand une ressource va atteindre son seuil critique
- **Alertes pod sans memory limit** : Détecte les pods à risque OOM (pas de `resources.limits.memory`)
- **Alerting multi-canal** : Webhook générique, Alertmanager, Slack, Email
- **API REST** : Consultation des anomalies, incidents et prédictions en temps réel
- **Stockage** : Persistance des données dans Elasticsearch

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        SREAgent                             │
│                                                             │
│  ┌──────────┐   ┌───────────┐   ┌──────────┐  ┌────────┐  │
│  │Collectors│──►│ Analyzers │──►│Correlator│─►│Alerter │  │
│  └──────────┘   └───────────┘   └──────────┘  └────────┘  │
│       │              │                │                      │
│  Prometheus      Metrics         Incidents              Slack│
│  MetricsSrv      Events          AnalysisResult        Email│
│  K8s API         Logs                                  Hook │
│                  Predictor                                   │
└─────────────────────────────────────────────────────────────┘
         │                                    │
    Elasticsearch                          API REST
    (stockage)                          /anomalies
                                        /incidents
                                        /predictions
```

## Structure du projet

```
src/
├── agent.py              # Orchestrateur principal (cycle collect → analyze → alert)
├── config.py             # Configuration via variables d'environnement
├── models.py             # Modèles de données Pydantic (NodeMetrics, PodMetrics, Anomaly...)
├── main.py               # Point d'entrée FastAPI
├── analyzer/
│   ├── metrics.py        # Détection d'anomalies (Z-score, IQR, seuils)
│   ├── events.py         # Analyse des événements Kubernetes
│   ├── logs.py           # Analyse des logs Elasticsearch
│   ├── correlator.py     # Corrélation anomalies → incidents
│   └── predictor.py      # Prédiction de saturation (régression linéaire)
├── alerter/
│   ├── webhook.py        # Webhook générique
│   ├── alertmanager.py   # Prometheus Alertmanager
│   ├── slack.py          # Slack
│   └── email.py          # Email SMTP
├── collector/
│   ├── prometheus.py     # Métriques Prometheus
│   ├── metrics_server.py # Kubernetes Metrics Server
│   └── k8s_api.py        # K8s API (events, states, pod limits, PVC, HPA...)
├── storage/
│   └── elasticsearch.py  # Persistance Elasticsearch
└── api/
    └── routes.py         # Endpoints REST (FastAPI)

tests/                    # 154 tests unitaires (pytest)
helm/kube-seer/           # Chart Helm pour déploiement Kubernetes
k8s/                      # Manifests Kubernetes (legacy)
```

## Installation

### Prérequis

- Python 3.11+
- Docker et Docker Compose
- Kubernetes + Helm 3.x (pour le déploiement)

### Développement local

```bash
git clone https://github.com/DamsDGN/kube-seer.git
cd kube-seer
make setup-dev
make test
make run-dev
```

### Déploiement Helm

```bash
# Développement
./helm-deploy.sh install dev

# Production
./helm-deploy.sh install prod
```

```bash
# Installation manuelle
kubectl create namespace monitoring
helm install kube-seer ./helm/kube-seer \
  --namespace monitoring \
  --set elasticsearch.url=http://elasticsearch:9200
```

## API REST

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Santé de l'agent |
| `GET /ready` | Disponibilité (vérifie ES, Prometheus) |
| `GET /status` | Statut complet du système |
| `GET /config` | Configuration active (sans secrets) |
| `GET /anomalies` | Anomalies détectées (filtrables par sévérité/namespace) |
| `GET /incidents` | Incidents corrélés |
| `GET /predictions` | Prédictions de saturation |
| `GET /alerts/stats` | Statistiques des alertes |
| `POST /analyze` | Déclencher une analyse manuelle |

## Configuration

Les paramètres principaux sont configurables via variables d'environnement :

```yaml
# Connexions
ELASTICSEARCH_URL: http://elasticsearch:9200
PROMETHEUS_URL: http://prometheus:9090

# Seuils d'alerte
THRESHOLDS_CPU_WARNING: 70.0
THRESHOLDS_CPU_CRITICAL: 85.0
THRESHOLDS_MEMORY_WARNING: 70.0
THRESHOLDS_MEMORY_CRITICAL: 85.0
THRESHOLDS_DISK_CRITICAL: 90.0

# Prédiction
PREDICTION_HORIZON_HOURS: 168   # Horizon de prédiction (7 jours par défaut)

# ML
ANOMALY_THRESHOLD: 0.05
MODEL_RETRAIN_INTERVAL: 3600

# Alerting
WEBHOOK_URL: https://your-webhook-url
SLACK_WEBHOOK: https://hooks.slack.com/services/...
```

## Tests

```bash
# Tests unitaires (154 tests, Python 3.11/3.12/3.13)
pytest tests/ -v

# Avec couverture
pytest tests/ --cov=src --cov-report=html
```

## CI/CD

Pipeline GitHub Actions sur chaque push et PR :

- Black + flake8 + mypy
- 154 tests unitaires sur Python 3.11, 3.12, 3.13
- Scan de sécurité Bandit
- Validation du chart Helm
- Build Docker multi-plateforme (AMD64/ARM64)
- Push sur Docker Hub
- Scan de vulnérabilités Trivy

Voir [docs/CI-CD.md](docs/CI-CD.md) pour les détails.

## Sécurité

- Utilisateur non-root dans le conteneur
- RBAC Kubernetes avec permissions minimales
- Secrets via variables d'environnement (jamais committés)
- Scan de vulnérabilités automatisé (Trivy + Bandit)

## Licence

[Creative Commons Attribution-NonCommercial-ShareAlike 4.0](LICENSE) — usage personnel et éducatif libre, usage commercial sur demande.

## Support

- Issues : [GitHub Issues](https://github.com/DamsDGN/kube-seer/issues)
- Discussions : [GitHub Discussions](https://github.com/DamsDGN/kube-seer/discussions)
