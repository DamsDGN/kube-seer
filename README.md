# Agent IA SRE pour Stack EFK

[![CI/CD Pipeline](https://github.com/DamsDGN/efk-sre/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/DamsDGN/efk-sre/actions/workflows/ci-cd.yml)
[![PR Validation](https://github.com/DamsDGN/efk-sre/actions/workflows/pr-validation.yml/badge.svg)](https://github.com/DamsDGN/efk-sre/actions/workflows/pr-validation.yml)
[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc-sa/4.0/)

Un agent d'intelligence artificielle dédié à l'analyse automatisée des métriques et logs d'une stack EFK (Elasticsearch, Fluentd, Kibana) déployée sur Kubernetes.

## 🎯 Objectifs

L'agent SRE utilise des techniques de Machine Learning pour :
- Détecter automatiquement les anomalies dans les métriques des pods
- Analyser les logs d'erreurs et identifier les patterns problématiques
- Corréler les anomalies métriques et logs pour un diagnostic précis
- Générer des alertes intelligentes avec contexte
- S'adapter en continu grâce à l'apprentissage automatique

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Elasticsearch │◄───┤   Agent SRE     │───►│   Alerting      │
│   (EFK Stack)   │    │   (Python/ML)   │    │   (Multi-canal) │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         ▲                       │                       │
         │                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Kubernetes    │    │   ML Models     │    │   Slack/Email   │
│   (Metrics)     │    │   (Auto-train)  │    │   /Webhooks     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 🧠 Composants IA/ML

### Analyseur de Métriques
- **Isolation Forest** : Détection d'anomalies dans les métriques CPU/mémoire
- **Features** : Usage, pics, tendances, contexte temporel
- **Seuils adaptatifs** basés sur l'historique

### Analyseur de Logs
- **TF-IDF Vectorizer** : Analyse sémantique des messages d'erreur
- **DBSCAN Clustering** : Regroupement d'erreurs similaires
- **Pattern Matching** : Détection d'erreurs connues (OOM, réseau, etc.)
- **Signatures d'erreurs** : Identification de nouveaux types d'erreurs

### Corrélation Intelligente
- Corrélation spatio-temporelle des anomalies
- Scoring de criticité basé sur la convergence des signaux
- Déduplication intelligente des alertes

## Installation et déploiement

### Prérequis

- Python 3.11+
- Docker et Docker Compose
- Kubernetes (optionnel, pour le déploiement en production)
- Helm 3.x (pour le déploiement Kubernetes)
- pipx pour l'isolation des outils

### Installation en mode développement

1. Cloner le repository :
```bash
git clone <repository-url>
cd efk-sre
```

2. Configurer l'environnement de développement :
```bash
make setup-dev
```

3. Lancer les tests :
```bash
make test
```

4. Démarrer l'agent en mode développement :
```bash
make run-dev
```

### Déploiement avec Docker

1. Construire l'image :
```bash
make docker-build
```

2. Lancer avec Docker Compose :
```bash
make docker-run
```

### Déploiement avec Helm (Recommandé)

#### Installation rapide

```bash
# Déploiement en développement
./helm-deploy.sh install dev

# Déploiement en production
./helm-deploy.sh install prod
```

#### Installation manuelle

1. Ajouter le namespace :
```bash
kubectl create namespace monitoring
```

2. Installer le chart :
```bash
# Environnement de développement
helm install efk-sre-agent ./helm/efk-sre-agent \
  --namespace monitoring \
  --values ./helm/efk-sre-agent/examples/values-dev.yaml

# Environnement de production
helm install efk-sre-agent ./helm/efk-sre-agent \
  --namespace monitoring \
  --values ./helm/efk-sre-agent/examples/values-prod.yaml
```

3. Vérifier le déploiement :
```bash
helm status efk-sre-agent -n monitoring
kubectl get pods -n monitoring -l app.kubernetes.io/name=efk-sre-agent
```

#### Gestion du déploiement Helm

```bash
# Mettre à jour
./helm-deploy.sh upgrade prod

# Voir le statut
./helm-deploy.sh status

# Désinstaller
./helm-deploy.sh uninstall
```

### Déploiement sur Kubernetes (legacy)

1. Appliquer les manifests :
```bash
kubectl apply -f k8s/
```

2. Vérifier le déploiement :
```bash
kubectl get pods -l app=efk-sre-agent
```

## 📊 API REST

L'agent expose une API REST pour le monitoring et la gestion :

### Endpoints principaux

```bash
# Santé de l'agent
GET /health

# Statut complet du système
GET /status

# Alertes récentes
GET /alerts?limit=50

# Statistiques des alertes
GET /alerts/stats

# Métriques actuelles des pods
GET /metrics/pods

# Logs récents avec erreurs
GET /logs/recent

# Déclenchement manuel d'analyse
POST /analyze/manual

# Réentraînement des modèles
POST /models/retrain
```

### Exemple de réponse d'alerte

```json
{
  "alerts": [
    {
      "type": "correlated_issue",
      "severity": "critical",
      "message": "Problème corrélé détecté sur le pod api-server-123",
      "timestamp": "2023-10-08T14:30:00Z",
      "metadata": {
        "pod_name": "api-server-123",
        "metric_alerts": 2,
        "log_alerts": 3,
        "correlation_score": 0.9
      }
    }
  ]
}
```

## 🔧 Configuration Avancée

### Seuils d'Alertes

```yaml
# Métriques
CPU_THRESHOLD_WARNING: 70.0
CPU_THRESHOLD_CRITICAL: 85.0
MEMORY_THRESHOLD_WARNING: 70.0
MEMORY_THRESHOLD_CRITICAL: 85.0

# ML
ANOMALY_THRESHOLD: 0.05
MODEL_RETRAIN_INTERVAL: 3600
MODEL_WINDOW_SIZE: 100
```

### Canaux d'Alerting

```yaml
# Webhook générique
WEBHOOK_URL: https://your-webhook-url

# Slack
SLACK_WEBHOOK: https://hooks.slack.com/services/...

# Email
EMAIL_SMTP_SERVER: smtp.gmail.com
EMAIL_USERNAME: alerts@company.com
EMAIL_RECIPIENTS: sre-team@company.com
```

## 🧪 Tests

```bash
# Tests unitaires
pytest tests/ -v

# Tests avec couverture
pytest tests/ --cov=src --cov-report=html

# Tests d'intégration
pytest tests/test_integration.py
```

## 📈 Monitoring et Observabilité

### Métriques Prometheus

L'agent expose des métriques Prometheus :

```
# Nombre d'alertes générées
sre_agent_alerts_total{severity="critical"}

# Durée d'analyse
sre_agent_analysis_duration_seconds

# Statut des modèles ML
sre_agent_model_accuracy{model="metrics"}
```

### Tableau de bord Grafana

Dashboards inclus pour :
- Statut de l'agent SRE
- Métriques d'analyse
- Performance des modèles ML
- Corrélation des alertes

## 🔍 Patterns d'Erreurs Détectés

L'agent reconnaît automatiquement :

- **OOM Killer** : `killed process.*out of memory`
- **Disk Full** : `no space left on device`
- **Network Issues** : `connection.*refused`, `timeout`
- **Database Errors** : `connection.*database.*failed`
- **Auth Problems** : `authentication.*failed`
- **Application Errors** : `null.*pointer.*exception`

## 🤖 Apprentissage Automatique

### Adaptation Continue

- **Réentraînement automatique** : Toutes les heures par défaut
- **Fenêtre glissante** : Garde les 100 derniers échantillons
- **Seuils dynamiques** : S'adaptent au comportement normal

### Modèles Persistants

Les modèles sont sauvegardés et rechargés :
```
/tmp/models/
├── metrics_model.pkl
├── metrics_scaler.pkl
├── log_vectorizer.pkl
└── log_classifier.pkl
```

## 🚨 Alertes et Notifications

### Niveaux de Sévérité

- **INFO** : Nouvelles erreurs détectées
- **WARNING** : Seuils dépassés, anomalies ML
- **CRITICAL** : Problèmes corrélés, seuils critiques

### Rate Limiting

Protection contre le spam :
- Max 1 alerte du même type/pod toutes les 5 minutes
- Déduplication intelligente
- Escalade basée sur la persistance

## 🛠️ Développement

### Structure du projet

```
efk-sre/
├── src/                    # Code source principal
│   ├── main.py            # Point d'entrée de l'application
│   ├── agent.py           # Agent SRE principal
│   ├── config.py          # Configuration
│   ├── models.py          # Modèles de données
│   ├── log_analyzer.py    # Analyseur de logs
│   ├── metrics_analyzer.py # Analyseur de métriques
│   ├── alerting.py        # Système d'alertes
│   └── api.py             # API REST
├── tests/                 # Tests unitaires
├── helm/                  # Charts Helm pour déploiement
│   └── efk-sre-agent/    # Chart principal
│       ├── Chart.yaml    # Métadonnées du chart
│       ├── values.yaml   # Valeurs par défaut
│       ├── templates/    # Templates Kubernetes
│       └── examples/     # Exemples de configuration
├── .github/workflows/     # Pipelines CI/CD
├── docs/                  # Documentation
├── k8s/                   # Manifests Kubernetes (legacy)
├── docker-compose.yml     # Configuration Docker Compose
├── Dockerfile            # Image Docker optimisée
├── helm-deploy.sh        # Script de déploiement Helm
├── Makefile              # Commandes de développement
└── requirements.txt      # Dépendances Python
```

## CI/CD et automatisation

Le projet inclut une pipeline CI/CD complète avec GitHub Actions :

- **Tests automatisés** : Tests unitaires sur Python 3.11, 3.12, 3.13
- **Sécurité** : Scan de vulnérabilités avec Trivy
- **Validation Helm** : Vérification des charts
- **Build Docker** : Images multi-plateforme (AMD64/ARM64)
- **Publication** : Push automatique sur Docker Hub
- **Releases** : Création automatique pour les tags

Voir [docs/CI-CD.md](docs/CI-CD.md) pour la configuration détaillée.

### Ajout de Nouveaux Analyseurs

1. Hériter de la classe de base `Analyzer`
2. Implémenter `analyze()` et `update_model()`
3. Ajouter au cycle principal dans `agent.py`

## 📝 Logs Structurés

L'agent utilise `structlog` pour des logs JSON :

```json
{
  "timestamp": "2023-10-08T14:30:00Z",
  "level": "info",
  "event": "Anomalie détectée",
  "pod_name": "api-server-123",
  "anomaly_score": -0.8,
  "model": "isolation_forest"
}
```

## 🔒 Sécurité

- **Utilisateur non-root** dans le conteneur
- **RBAC Kubernetes** avec permissions minimales
- **Secrets** pour les credentials sensibles
- **Réseau** : Pas d'exposition externe par défaut

## 🚀 Roadmap

- [ ] Support multi-cluster
- [ ] Interface web pour le tuning des modèles
- [ ] Intégration avec Prometheus Alertmanager
- [ ] Support des métriques custom
- [ ] Auto-scaling basé sur la charge
- [ ] Détection de dérive des modèles
- [ ] Explication des prédictions (XAI)

## 🤝 Contribution

Les contributions sont les bienvenues ! Ce projet suit les principes open source :

1. Fork le projet
2. Créer une branche feature (`git checkout -b feature/amazing-feature`)
3. Commit les changements (`git commit -m 'Add amazing feature'`)
4. Push vers la branche (`git push origin feature/amazing-feature`)
5. Ouvrir une Pull Request

### Code de conduite
- Respecter les bonnes pratiques Python (PEP 8)
- Ajouter des tests pour les nouvelles fonctionnalités
- Documenter le code et les APIs
- Maintenir la compatibilité backwards

## 📄 Licence

Ce projet est sous licence **Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International**.

### ✅ Autorisé
- ✅ Utilisation personnelle et éducative
- ✅ Modification et redistribution
- ✅ Utilisation dans des projets open source
- ✅ Recherche et développement académique

### ❌ Restrictions
- ❌ Usage commercial sans autorisation
- ❌ Vente du logiciel ou de services basés dessus
- ❌ Utilisation dans des produits commerciaux

### 💼 Usage commercial
Pour un usage commercial, contactez l'auteur pour obtenir une licence commerciale.

Voir le fichier [LICENSE](LICENSE) pour les détails complets.

## 📞 Support

- **Issues** : [GitHub Issues](https://github.com/DamsDGN/efk-sre/issues)
- **Documentation** : [Wiki du projet](https://github.com/DamsDGN/efk-sre/wiki)
- **Discussions** : [GitHub Discussions](https://github.com/DamsDGN/efk-sre/discussions)
- **Commercial** : Contactez l'auteur pour les licences commerciales

---

**Fait avec ❤️ par l'équipe SRE**