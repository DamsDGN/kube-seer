# GitHub Actions Status

![CI/CD Pipeline](https://github.com/DamsDGN/kube-seer/actions/workflows/ci-cd.yml/badge.svg)

## État du pipeline CI/CD

### Workflow unifié (`ci-cd.yml`)
- ✅ Tests multi-version Python (3.11, 3.12, 3.13)
- ✅ Validation Helm
- ✅ Build Docker adaptatif (test pour PR, publication pour push)
- ✅ Scan de sécurité Trivy
- ✅ Publication automatique sur Docker Hub
- ✅ Releases GitHub automatiques

### Comportement intelligent
- **Pull Requests** → Tests + validation + build test
- **Push main/develop** → Pipeline complet + publication
- **Tags v*** → Release + packaging Helm

## Images Docker disponibles

```bash
# Latest stable
docker pull damsdgn29/kube-seer:latest

# Version spécifique
docker pull damsdgn29/kube-seer:v1.0.0

# Branch develop
docker pull damsdgn29/kube-seer:develop
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

- [Actions GitHub](https://github.com/DamsDGN/kube-seer/actions)
- [Docker Hub](https://hub.docker.com/r/damsdgn29/kube-seer)
- [Releases](https://github.com/DamsDGN/kube-seer/releases)
