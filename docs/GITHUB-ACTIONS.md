# ## Pipeline CI/CD

Le projet utilise un **workflow unique** GitHub Actions optimisé qui s'adapte automatiquement selon le contexte :

- **`.github/workflows/ci-cd.yml`** : Workflow principal unifié

## Pipeline unifié

### Déclencheurs
```yaml
on:
  push:
    branches: [ main, develop ]
    tags: [ 'v*' ]
  pull_request:
    branches: [ main, develop ]
```

### Comportement adaptatif

#### Pour les **Pull Requests** :
- ✅ Tests multi-versions Python (3.11, 3.12, 3.13)
- ✅ Validation Helm
- ✅ **Test de build Docker** (sans publication)
- ❌ Pas de publication sur Docker Hub

#### Pour les **Push main/develop** :
- ✅ Tests multi-versions Python
- ✅ Validation Helm
- ✅ **Build et publication Docker**
- ✅ Scan de sécurité
- ✅ Publication sur Docker Hub

#### Pour les **Tags v*** :
- ✅ Pipeline complet
- ✅ **Release GitHub automatique**
- ✅ Chart Helm packagéub Actions - CI/CD

## Vue d'ensemble

Le projet utilise GitHub Actions pour l'intégration et le déploiement continus avec deux workflows principaux :

- **CI/CD Pipeline** (`.github/workflows/ci-cd.yml`) : Pipeline complet pour les branches main/develop et les tags
- **PR Validation** (`.github/workflows/pr-validation.yml`) : Validation rapide pour les Pull Requests

## Pipeline CI/CD Principal

### Déclencheurs
```yaml
on:
  push:
    branches: [ main, develop ]
    tags: [ 'v*' ]
  pull_request:
    branches: [ main ]
```

### Jobs et étapes

#### 1. Test (Matrice multi-version Python)
- **Python** : 3.11, 3.12, 3.13
- **Formatage** : Vérification Black
- **Lint** : flake8 avec règles personnalisées
- **Type checking** : mypy
- **Tests unitaires** : pytest
- **Sécurité** : bandit pour l'analyse de sécurité

#### 2. Validation Helm
- **Lint** : Validation de la syntaxe du chart
- **Template** : Test de génération des manifests
- **Versions** : Helm 3.12.0

#### 3. Build et Push Docker
- **Plateformes** : linux/amd64, linux/arm64
- **Registry** : Docker Hub
- **Cache** : GitHub Actions cache
- **Scan sécurité** : Anchore pour les vulnérabilités
- **Tags automatiques** : basés sur branches/tags

#### 4. Release GitHub
- **Déclencheur** : Tags v*
- **Artifacts** : Charts Helm packagés
- **Release notes** : Générées automatiquement

## Configuration des secrets

### Secrets requis dans GitHub

Allez dans **Settings > Secrets and variables > Actions** :

1. **DOCKERHUB_USERNAME**
   ```
   Votre nom d'utilisateur Docker Hub
   ```

2. **DOCKERHUB_TOKEN**
   ```
   Token d'accès Docker Hub (pas le mot de passe)
   ```

### Création d'un token Docker Hub

1. Connectez-vous à [Docker Hub](https://hub.docker.com/)
2. **Account Settings > Security > New Access Token**
3. Nom : `GitHub Actions CI/CD`
4. Permissions : Read, Write, Delete
5. Copiez le token généré

## Stratégie de tags Docker

Le pipeline génère automatiquement les tags suivants :

### Pour les branches
```bash
# Branch main
damsdgn/kube-seer:latest
damsdgn/kube-seer:main-<sha>

# Branch develop
damsdgn/kube-seer:develop
damsdgn/kube-seer:develop-<sha>
```

### Pour les tags de release
```bash
# Tag v1.2.3
damsdgn/kube-seer:v1.2.3
damsdgn/kube-seer:1.2.3
damsdgn/kube-seer:1.2
damsdgn/kube-seer:1
damsdgn/kube-seer:latest
```

## Workflow PR Validation

Pipeline rapide pour les Pull Requests :
- Tests unitaires sur Python 3.13
- Vérification du formatage et lint
- Validation Helm
- Test de build Docker (sans push)

## Utilisation

### Développement normal
```bash
# Les pushes sur develop déclenchent le pipeline
git push origin develop

# Les pushes sur main déclenchent le pipeline complet
git push origin main
```

### Création d'une release
```bash
# Créer et pusher un tag pour déclencher une release
git tag v1.0.0
git push origin v1.0.0

# Une release GitHub sera créée automatiquement avec :
# - Notes de release générées
# - Chart Helm packagé
# - Image Docker publiée
```

### Pull Requests
```bash
# Les PR vers main/develop déclenchent la validation
gh pr create --title "Nouvelle fonctionnalité" --body "Description"
```

## Monitoring et debugging

### Voir les runs
```bash
# Lister les runs récents
gh run list

# Voir les détails d'un run
gh run view <run-id>

# Voir les logs d'un job
gh run view <run-id> --log
```

### Artifacts
- **Test results** : Résultats des tests par version Python
- **Vulnerability scans** : Rapports de sécurité
- **Helm packages** : Charts packagés pour les releases

## Optimisations

### Cache
- **Pip dependencies** : Cache des dépendances Python
- **Docker layers** : Cache GitHub Actions pour builds rapides

### Sécurité
- **Scan Anchore** : Détection des vulnérabilités
- **Bandit** : Analyse de sécurité du code Python
- **Multi-stage builds** : Images optimisées

### Performance
- **Builds parallèles** : Tests sur multiple versions Python
- **Cache Docker** : Réutilisation des layers
- **Build multi-plateforme** : AMD64 + ARM64

## Troubleshooting

### Erreurs communes

#### Secrets manquants
```
Error: Username and password required
```
**Solution** : Vérifier que DOCKERHUB_USERNAME et DOCKERHUB_TOKEN sont configurés

#### Échec de build Docker
```
failed to solve: process "/bin/sh -c pip install..." didn't complete successfully
```
**Solution** : Vérifier le requirements.txt et la syntaxe du Dockerfile

#### Helm validation échoue
```
Error: chart metadata is missing
```
**Solution** : Vérifier Chart.yaml et la structure du chart

### Commands de debug local

```bash
# Tester le build Docker localement
docker build -t kube-seer:test .

# Valider Helm localement
helm lint ./helm/kube-seer/

# Exécuter les tests comme en CI
python -m pytest tests/ -v

# Vérifier le formatage
black --check src/ tests/
```
