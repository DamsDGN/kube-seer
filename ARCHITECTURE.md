# 🏗️ Architecture et Justifications Techniques

## 🐍 Pourquoi pipx + venv ?

### Séparation des Préoccupations

1. **Outils de développement (pipx)** : Installés globalement, disponibles partout
   - `black`, `flake8`, `mypy`, `pytest`, `pre-commit`
   - Évite les conflits de versions entre projets
   - Mise à jour indépendante des dépendances du projet

2. **Dépendances du projet (venv)** : Isolées dans l'environnement virtuel
   - `elasticsearch`, `kubernetes`, `scikit-learn`, `fastapi`
   - Versions contrôlées par requirements.txt
   - Reproductibilité garantie

### Avantages

- **Isolation complète** : Pas de pollution de l'environnement système
- **Reproductibilité** : Mêmes versions sur tous les environnements
- **Sécurité** : Réduction des risques de typosquatting
- **Performance** : Outils pipx compilés une seule fois

## 🔧 Architecture du Projet

```
efk-sre/
├── 📜 Scripts de Setup
│   ├── setup.sh              # Configuration pipx + venv
│   ├── activate.sh            # Activation rapide
│   └── test.sh               # Tests sans dépendances
├── 🐍 Code Python
│   └── src/
│       ├── agent.py          # Agent principal IA
│       ├── metrics_analyzer.py  # ML pour métriques
│       ├── log_analyzer.py   # NLP pour logs
│       └── ...
├── 🐳 Infrastructure
│   ├── Dockerfile            # Image de production
│   ├── k8s/                  # Manifestes Kubernetes
│   └── deploy.sh             # Déploiement Kind
└── 🧪 Développement
    ├── .pre-commit-config.yaml
    ├── Makefile              # Commandes simplifiées
    └── tests/
```

## 🚀 Workflow de Développement

### 1. Configuration Initiale (Une Fois)

```bash
make setup                    # Installe tout avec pipx + venv
```

### 2. Développement Quotidien

```bash
source activate.sh           # Activer l'environnement
# Développer...
make format                  # Formater automatiquement
make lint                    # Vérifier la qualité
make test-quick             # Tests rapides
git commit                  # Les hooks pre-commit s'exécutent
```

### 3. Tests et Déploiement

```bash
make test-unit              # Tests complets
make deploy-quick           # Déployer sur Kind
make test-api              # Tester l'API déployée
```

## 🛡️ Sécurité et Bonnes Pratiques

### Isolation des Secrets

- **Jamais de secrets en dur** dans le code
- **Variables d'environnement** pour la configuration
- **Secrets Kubernetes** pour la production
- **Fichiers .env locaux** pour le développement (non commités)

### Qualité du Code

- **Pre-commit hooks** : Vérifications automatiques avant commit
- **Type checking** : mypy pour la robustesse
- **Formatage automatique** : black pour la consistance
- **Tests automatisés** : pytest avec couverture

### Containerisation

- **Multi-stage build** : Image de production optimisée
- **Non-root user** : Sécurité runtime
- **Health checks** : Monitoring intégré
- **Ressources limitées** : Pas de fuite mémoire

## 🔬 Choix Techniques ML/IA

### Détection d'Anomalies Métriques

**Isolation Forest** : Choisi pour sa robustesse aux données bruitées
- Pas besoin de données étiquetées
- Efficace sur des datasets de taille moyenne
- Résistant aux outliers "normaux"

### Analyse de Logs

**TF-IDF + DBSCAN** : Pipeline classique mais éprouvé
- Vectorisation sémantique des messages
- Clustering automatique des erreurs similaires
- Détection de nouveaux patterns

### Corrélation Intelligente

**Score de corrélation** basé sur :
- Proximité temporelle des événements
- Même pod/namespace affecté
- Convergence des signaux (métriques + logs)

## 📊 Observabilité

### Métriques Exposées

```python
# Prometheus metrics automatiques
sre_agent_alerts_total{severity="critical"}
sre_agent_analysis_duration_seconds
sre_agent_model_accuracy{model="metrics"}
```

### Logs Structurés

```json
{
  "timestamp": "2023-10-08T14:30:00Z",
  "level": "info",
  "event": "anomaly_detected",
  "pod_name": "api-server-123",
  "anomaly_score": -0.8,
  "correlation_id": "abc-123"
}
```

## 🔮 Évolutivité

### Architecture Modulaire

Chaque analyseur est indépendant :
- Ajout facile de nouveaux types d'analyse
- Remplacement de modèles ML sans impact
- Scaling horizontal possible

### Points d'Extension

1. **Nouveaux Analyseurs** : Hériter de la classe de base
2. **Nouveaux Canaux d'Alerte** : Plugins dans AlertManager
3. **Nouveaux Modèles ML** : Interface standardisée
4. **Nouvelles Sources** : Adaptateurs pour autres stacks

## 🎯 Objectifs de Performance

- **Latence d'analyse** : < 5 minutes pour la détection
- **Débit** : Support de 1000+ pods simultanés
- **Précision** : < 5% de faux positifs après entraînement
- **Disponibilité** : 99.9% uptime de l'agent

Cette architecture garantit :
✅ **Simplicité** de développement et déploiement
✅ **Robustesse** pour la production
✅ **Évolutivité** pour la croissance
✅ **Sécurité** pour un repo public