# 🚀 Guide de Démarrage Rapide avec Kind et pipx

Ce guide vous permet de déployer et tester l'agent SRE EFK localement avec Kind et pipx.

## Prérequis

1. **Python 3.11+** avec pipx
2. **Docker** : https://docs.docker.com/get-docker/
3. **kubectl** : https://kubernetes.io/docs/tasks/tools/

### Installation rapide de pipx

```bash
# Installation de pipx
python3 -m pip install --user pipx
python3 -m pipx ensurepath

# Redémarrer le terminal, puis vérifier
pipx --version
```

### Installation de Kind avec pipx

```bash
# Option 1: Avec pipx (recommandé)
pipx install kind-python

# Option 2: Installation directe
curl -Lo ./kind https://kind.sigs.k8s.io/dl/latest/kind-linux-amd64
chmod +x ./kind
sudo mv ./kind /usr/local/bin/kind
```

## 🏃 Démarrage Ultra-Rapide

### Configuration automatique

```bash
# Clone le repo (si pas déjà fait)
git clone https://github.com/DamsDGN/efk-sre-agent.git
cd efk-sre-agent

# Configuration complète en une commande
make setup

# Activation de l'environnement
source activate.sh

# Tests rapides
make test-quick

# Déploiement avec Kind
make deploy
```

## 🔧 Configuration Détaillée

### 1. Configuration de l'environnement

```bash
# Configuration complète (outils pipx + venv + hooks)
./setup.sh install

# Ou étape par étape
./setup.sh tools     # Outils pipx uniquement
./setup.sh venv      # Environnement virtuel uniquement
./setup.sh hooks     # Pre-commit hooks uniquement
```

### 2. Activation de l'environnement

```bash
# Script d'activation rapide
source activate.sh

# Ou manuellement
source .venv/bin/activate
```

### 3. Vérification et tests

```bash
# Vérifier l'environnement
make dev-check

# Tests rapides
./test.sh

# Tests unitaires complets
make test-unit

# Vérification du code
make lint
make format
make type-check
```

### 4. Déploiement

```bash
# Première installation complète
make deploy

# Redéploiements rapides
make deploy-quick

# Mise à jour après modifications
make update
```

## 💻 Développement Quotidien

### Workflow recommandé

```bash
# 1. Activer l'environnement (à chaque session)
source activate.sh

# 2. Développer et tester
make test-quick        # Tests rapides
make format           # Formater le code
make lint            # Vérifier la qualité

# 3. Déployer les changements
make deploy-quick

# 4. Tester l'API
make test-api
```

### Outils pipx disponibles

Installés globalement, utilisables partout :
- `black` : Formatage automatique
- `flake8` : Analyse statique
- `mypy` : Vérification de types
- `pytest` : Tests unitaires  
- `pre-commit` : Hooks Git automatiques

## 🔧 Développement

### Redéploiement rapide après modifications

```bash
# Pour les modifications de code uniquement
./deploy.sh deploy-quick

# Pour un rebuild complet
./deploy.sh update
```

### Commandes utiles

```bash
# Voir tous les pods
kubectl get pods -n monitoring

# Logs en temps réel
kubectl logs -f -n monitoring deployment/efk-sre-agent

# Shell dans le pod
kubectl exec -it -n monitoring deployment/efk-sre-agent -- /bin/bash

# Forward de l'API
kubectl port-forward -n monitoring svc/efk-sre-agent 8080:8080
```

## 🧪 Tests avec Elasticsearch simulé

Pour les tests sans stack EFK complète :

```bash
# Déployer Elasticsearch de dev
kubectl apply -f k8s/local-dev.yaml.example

# Attendre que ES soit prêt
kubectl wait --for=condition=ready pod -l app=elasticsearch-dev -n monitoring --timeout=300s

# Puis déployer l'agent
./deploy.sh deploy-quick
```

## 🗑️ Nettoyage

```bash
# Supprimer l'application uniquement
./deploy.sh cleanup

# Supprimer le cluster Kind complet
./deploy.sh cleanup-kind
```

## 🐛 Dépannage

### L'agent ne démarre pas

```bash
# Vérifier les logs
kubectl logs -n monitoring deployment/efk-sre-agent

# Vérifier la configuration
kubectl get configmap -n monitoring efk-sre-agent-config -o yaml
kubectl get secret -n monitoring efk-sre-agent-secrets -o yaml
```

### Problèmes de réseau

```bash
# Vérifier les services
kubectl get svc -n monitoring

# Tester la connectivité interne
kubectl run test-pod --image=busybox -it --rm -- /bin/sh
# Dans le pod: nslookup efk-sre-agent.monitoring.svc.cluster.local
```

### Rechargement de l'image

```bash
# Si l'image ne se met pas à jour
./deploy.sh build  # Rebuild et recharge dans Kind
kubectl rollout restart deployment/efk-sre-agent -n monitoring
```

## 📋 Configuration

Le fichier `.env` est créé automatiquement avec des valeurs par défaut.
Pour la production, modifiez ces valeurs :

```bash
# Éditer la configuration
cp .env.example .env
nano .env  # Modifier selon vos besoins
```

## 🔗 URLs utiles

- **API Health** : http://localhost:8080/health
- **API Status** : http://localhost:8080/status  
- **API Docs** : http://localhost:8080/docs
- **Métriques** : http://localhost:8080/metrics

## 🎯 Prochaines étapes

1. Déployer une vraie stack EFK
2. Configurer les alertes (Slack/Email)
3. Ajuster les seuils selon votre environnement
4. Monitorer les performances des modèles ML