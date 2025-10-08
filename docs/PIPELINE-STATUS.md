# GitHub Actions Status

![CI/CD Pipeline](https://github.com/DamsDGN/efk-sre/actions/workflows/ci-cd.yml/badge.svg)
![PR Validation](https://github.com/DamsDGN/efk-sre/actions/workflows/pr-validation.yml/badge.svg)

## État du pipeline CI/CD

### Workflow principal (`ci-cd.yml`)
- ✅ Tests multi-version Python (3.11, 3.12, 3.13)  
- ✅ Validation Helm
- ✅ Build Docker multi-plateforme
- ✅ Scan de sécurité
- ✅ Publication automatique sur Docker Hub
- ✅ Releases GitHub automatiques

### Workflow PR (`pr-validation.yml`)
- ✅ Tests rapides
- ✅ Validation du formatage
- ✅ Test de build Docker

## Images Docker disponibles

```bash
# Latest stable
docker pull damsdgn/efk-sre-agent:latest

# Version spécifique  
docker pull damsdgn/efk-sre-agent:v1.0.0

# Branch develop
docker pull damsdgn/efk-sre-agent:develop
```

## Configuration requise

### Secrets GitHub
- `DOCKERHUB_USERNAME` : Nom d'utilisateur Docker Hub
- `DOCKERHUB_TOKEN` : Token d'accès Docker Hub

### Déclencheurs
- **Push** sur `main` ou `develop` → Pipeline complet
- **Tags** `v*` → Release + publication
- **Pull Requests** → Validation rapide

## Monitoring

- [Actions GitHub](https://github.com/DamsDGN/efk-sre/actions)
- [Docker Hub](https://hub.docker.com/r/damsdgn/efk-sre-agent)
- [Releases](https://github.com/DamsDGN/efk-sre/releases)