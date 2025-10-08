# Agent IA SRE pour Stack EFK

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

## 🚀 Installation et Déploiement

### Prérequis
- Kubernetes cluster (ou Kind pour le développement local)
- Python 3.11+
- Docker
- Accès à Elasticsearch
- Permissions Kubernetes (lecture pods/metrics)

### 🏃 Démarrage Rapide avec Kind et pipx

```bash
# Configuration complète de l'environnement
git clone https://github.com/DamsDGN/efk-sre.git
cd efk-sre
make setup

# Activation et tests
source activate.sh
make test-quick

# Déploiement local
make deploy
```

Voir [QUICKSTART.md](QUICKSTART.md) pour le guide détaillé.

### 1. Installation des dépendances

```bash
pip install -r requirements.txt
```

### 2. Configuration

Copier le fichier d'exemple et configurer :

```bash
cp .env.example .env
# Éditer .env avec vos paramètres
```

Variables principales :
```bash
ELASTICSEARCH_URL=http://elasticsearch:9200
ELASTICSEARCH_USER=elastic
ELASTICSEARCH_PASSWORD=your-password
METRICS_INDEX=metricbeat-*
LOGS_INDEX=fluentd-*
ANALYSIS_INTERVAL=300
```

### 3. Déploiement sur Kubernetes (Production)

```bash
# Créer le namespace de monitoring
kubectl create namespace monitoring

# Configurer les secrets (IMPORTANT: Utilisez vos vraies valeurs!)
kubectl create secret generic efk-sre-agent-secrets \
  --from-literal=ELASTICSEARCH_PASSWORD=your-real-password \
  -n monitoring

# Déployer l'agent
kubectl apply -f k8s/deployment.yaml
```

### 4. Déploiement local avec Kind (Développement)

```bash
# Utiliser le script automatisé
./deploy.sh deploy

# Ou étape par étape
./deploy.sh setup-kind    # Créer le cluster Kind
./deploy.sh deploy-quick  # Déployer l'application
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

### Structure du Code

```
src/
├── agent.py          # Agent principal
├── config.py         # Configuration
├── models.py         # Modèles de données
├── metrics_analyzer.py # Analyse métriques + ML
├── log_analyzer.py   # Analyse logs + NLP
├── alerting.py       # Gestionnaire d'alertes
├── api.py           # API REST
└── main.py          # Point d'entrée
```

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

1. Fork le projet
2. Créer une branche feature (`git checkout -b feature/amazing-feature`)
3. Commit les changements (`git commit -m 'Add amazing feature'`)
4. Push vers la branche (`git push origin feature/amazing-feature`)
5. Ouvrir une Pull Request

## 📄 Licence

Ce projet est sous licence MIT. Voir le fichier `LICENSE` pour plus de détails.

## 📞 Support

- **Issues** : Utiliser GitHub Issues
- **Documentation** : Wiki du projet
- **Discussions** : GitHub Discussions

---

**Fait avec ❤️ par l'équipe SRE**