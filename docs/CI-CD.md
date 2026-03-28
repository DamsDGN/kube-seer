# CI/CD Configuration

## GitHub Secrets

For the CI/CD pipeline to work, configure the following secrets in your GitHub repository:

### Required Secrets

1. **DOCKERHUB_USERNAME** — Your Docker Hub username
2. **DOCKERHUB_TOKEN** — Docker Hub access token (recommended over password)

### How to Configure Secrets

1. Go to your GitHub repository
2. Click **Settings** > **Secrets and variables** > **Actions**
3. Click **New repository secret**
4. Add each secret:

#### DOCKERHUB_USERNAME
- **Name**: `DOCKERHUB_USERNAME`
- **Secret**: Your Docker Hub username

#### DOCKERHUB_TOKEN
- **Name**: `DOCKERHUB_TOKEN`
- **Secret**: Your Docker Hub access token

### Create a Docker Hub Token

1. Log in to [Docker Hub](https://hub.docker.com/)
2. Go to **Account Settings** > **Security**
3. Click **New Access Token**
4. Give the token a name (e.g. "GitHub Actions CI/CD")
5. Select appropriate permissions (Read, Write, Delete)
6. Copy the generated token and use it as `DOCKERHUB_TOKEN`

## CI/CD Pipeline

The pipeline is configured for:

### Triggers
- Push to `main`
- Pull requests targeting `main`
- Tags starting with `v*`

### Main Steps

1. **Tests** — Unit tests on Python 3.11, 3.12, 3.13
2. **Security** — Vulnerability scan with Trivy + Bandit
3. **Helm** — Chart validation
4. **Docker** — Multi-platform build (linux/amd64, linux/arm64)
5. **Publish** — Automatic push to Docker Hub
6. **Release** — Automatic GitHub release for tags

### Environment Variables

The pipeline uses:

- `REGISTRY` — `docker.io` (Docker Hub)
- `IMAGE_NAME` — `kube-seer`
- `IMAGE_TAG` — Generated from commit SHA or tag

### Security

- Vulnerability scanning with Trivy
- Multi-stage images to reduce attack surface
- Non-root user in container
- No hardcoded secrets in code

## Usage

### Development
- Pushes trigger tests and build
- Images tagged with `<branch>-<sha>`

### Production
- Pushes to `main` trigger the full pipeline
- Images tagged with `latest` and `main-<sha>`

### Releases
- Create a tag `v1.0.0` to trigger a release
- Image tagged with `v1.0.0` and `latest`
- GitHub release created automatically

## Useful Commands

```bash
# Create a release tag
git tag v1.0.0
git push origin v1.0.0

# Check pipeline status
gh run list

# View a run's details
gh run view <run-id>
```
