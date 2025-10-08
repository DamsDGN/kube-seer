# Configuration CI/CD

## Configuration des secrets GitHub

Pour que le pipeline CI/CD fonctionne correctement, vous devez configurer les secrets suivants dans votre repository GitHub :

### Secrets requis

1. **DOCKERHUB_USERNAME** : Votre nom d'utilisateur Docker Hub
2. **DOCKERHUB_TOKEN** : Token d'accès Docker Hub (recommandé plutôt que le mot de passe)

### Comment configurer les secrets

1. Allez dans votre repository GitHub
2. Cliquez sur **Settings** > **Secrets and variables** > **Actions**
3. Cliquez sur **New repository secret**
4. Ajoutez chaque secret :

#### DOCKERHUB_USERNAME
- **Name** : `DOCKERHUB_USERNAME`
- **Secret** : Votre nom d'utilisateur Docker Hub

#### DOCKERHUB_TOKEN
- **Name** : `DOCKERHUB_TOKEN`  
- **Secret** : Votre token d'accès Docker Hub

### Créer un token Docker Hub

1. Connectez-vous à [Docker Hub](https://hub.docker.com/)
2. Allez dans **Account Settings** > **Security**
3. Cliquez sur **New Access Token**
4. Donnez un nom au token (ex: "GitHub Actions CI/CD")
5. Sélectionnez les permissions appropriées (Read, Write, Delete)
6. Copiez le token généré et utilisez-le comme `DOCKERHUB_TOKEN`

## Pipeline CI/CD

Le pipeline est configuré pour :

### Déclencheurs
- Push sur `main` et `develop`
- Pull requests vers `main`
- Tags commençant par `v*`

### Étapes principales

1. **Tests** : Tests unitaires sur Python 3.11, 3.12, 3.13
2. **Sécurité** : Scan de vulnérabilités avec Trivy
3. **Helm** : Validation du chart Helm
4. **Docker** : Build multi-plateforme (linux/amd64, linux/arm64)
5. **Publication** : Push automatique sur Docker Hub
6. **Release** : Création automatique de releases GitHub pour les tags

### Variables d'environnement

Le pipeline utilise les variables suivantes :

- `REGISTRY` : `docker.io` (Docker Hub)
- `IMAGE_NAME` : `efk-sre-agent`
- `IMAGE_TAG` : Généré automatiquement basé sur le SHA du commit ou le tag

### Sécurité

- Scan de vulnérabilités avec Trivy
- Images multi-stage pour réduire la surface d'attaque
- Utilisateur non-root dans le conteneur
- Pas de secrets hardcodés dans le code

## Utilisation

### Développement
- Les pushes sur `develop` déclenchent les tests et le build
- Les images sont taguées avec `develop-<sha>`

### Production
- Les pushes sur `main` déclenchent le pipeline complet
- Les images sont taguées avec `latest` et `main-<sha>`

### Releases
- Créez un tag `v1.0.0` pour déclencher une release
- L'image sera taguée avec `v1.0.0` et `latest`
- Une release GitHub sera créée automatiquement

## Commandes utiles

```bash
# Créer un tag pour release
git tag v1.0.0
git push origin v1.0.0

# Vérifier le statut du pipeline
gh run list

# Voir les détails d'un run
gh run view <run-id>
```