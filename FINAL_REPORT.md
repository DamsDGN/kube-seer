# kube-seer — Rapport Final

## Projet terminé — 6 phases implémentées

### Phases réalisées

| Phase | Description | Statut |
|-------|-------------|--------|
| Phase 1 | Foundations — modèles, config, agent skeleton, API, stockage ES | ✅ |
| Phase 2 | Anomaly Detection — Z-score, IQR, seuils adaptatifs | ✅ |
| Phase 3 | Alerting — Webhook, Alertmanager, Slack, Email | ✅ |
| Phase 4 | Correlation — regroupement anomalies → incidents | ✅ |
| Phase 5 | Prediction — régression linéaire, time-to-saturation, endpoint /predictions | ✅ |
| Phase 6 | Minor gaps — pod limits, prédictions pod, anomalies policy, PVC/HPA/NetPol/Quota/Ingress | ✅ |

### Fonctionnalités clés

#### Collecte multi-sources
- Prometheus (métriques nodes et pods)
- Kubernetes Metrics Server
- Kubernetes API : events, resource states, pod limits, PVC, HPA, NetworkPolicy, ResourceQuota, Ingress

#### Détection d'anomalies
- Analyse statistique : Z-score et IQR sur CPU, mémoire, disque
- Analyse des événements Kubernetes
- Analyse des logs Elasticsearch
- Détection de politique : pods sans `resources.limits.memory` (risque OOM)

#### Corrélation d'incidents
- Regroupement spatio-temporel des anomalies en incidents
- Scoring de criticité par convergence de signaux

#### Prédiction de saturation
- Régression linéaire sur historique glissant
- Prédiction nodes (CPU, mémoire, disque) et pods (CPU%, mémoire%)
- Horizon configurable via `PREDICTION_HORIZON_HOURS` (défaut 168h)
- Confiance basée sur R²

#### Alerting multi-canal
- Webhook générique, Prometheus Alertmanager, Slack, Email SMTP
- Rate limiting et déduplication

### Qualité

- **154/154 tests unitaires** — Python 3.11, 3.12, 3.13
- **Flake8 + Black + mypy** — zéro erreur
- **CI/CD GitHub Actions** — pipeline complet sur chaque PR
- **Scan de sécurité** — Bandit (code) + Trivy (image Docker)
- **TDD** — tests écrits avant l'implémentation sur toutes les phases

### Infrastructure

- Image Docker multi-stage, multi-plateforme (AMD64/ARM64)
- Chart Helm production-ready avec RBAC, secrets, ServiceMonitor
- Pipeline CI/CD : tests → build → push Docker Hub → release GitHub

### Architecture finale

```
src/
├── agent.py              # Orchestrateur (collect → analyze → alert → store)
├── config.py             # Configuration Pydantic
├── models.py             # Modèles de données (NodeMetrics, PodMetrics, Anomaly, Prediction...)
├── analyzer/
│   ├── metrics.py        # Détection d'anomalies
│   ├── events.py         # Événements K8s
│   ├── logs.py           # Logs ES
│   ├── correlator.py     # Corrélation → incidents
│   └── predictor.py      # Prédiction de saturation
├── alerter/              # Webhook, Alertmanager, Slack, Email
├── collector/            # Prometheus, MetricsServer, K8s API
├── storage/              # Elasticsearch
└── api/                  # REST API FastAPI
```

---
*Rapport mis à jour le 28 mars 2026 — kube-seer*
