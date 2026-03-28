# Security Guide

## ⚠️ IMPORTANT: Sensitive Information

This project is **PUBLIC** on GitHub. Never commit:

### ❌ Never Commit

- Elasticsearch passwords
- API tokens
- Slack webhooks with tokens
- Email credentials
- Certificates / private keys
- Internal URLs with embedded credentials
- `.env` files with real values

### ✅ Protections in Place

The following are automatically ignored by `.gitignore`:
- `.env`
- `.env.local`
- `.env.production`
- `k8s/secrets.yaml`
- `k8s/local-*.yaml`
- `*.key`, `*.pem`, `*.crt`
- `secrets/`, `credentials/`

## Best Practices

### 1. Environment Variables

```bash
# Use environment variables for secrets
export ELASTICSEARCH_PASSWORD="real-secret-value"
export SLACK_WEBHOOK="https://hooks.slack.com/services/real/webhook/url"

# Or a local .env file (not committed)
cp .env.example .env
# Edit .env with real values
```

### 2. Kubernetes Secrets

```bash
# Create secrets from a file
kubectl create secret generic kube-seer-secrets \
  --from-env-file=.env \
  -n monitoring

# Or individually
kubectl create secret generic kube-seer-secrets \
  --from-literal=ELASTICSEARCH_PASSWORD="real-value" \
  -n monitoring
```

### 3. Helm Chart — Inline or External Secret

```bash
# Inline password (creates a Secret in the chart)
helm install kube-seer ./helm/kube-seer \
  --set elasticsearch.url=http://elasticsearch:9200 \
  --set elasticsearch.username=elastic \
  --set elasticsearch.password=real-password

# Reference an existing secret
helm install kube-seer ./helm/kube-seer \
  --set elasticsearch.url=http://elasticsearch:9200 \
  --set elasticsearch.secretRef=my-existing-secret
```

## Secret Management in Production

### 1. Sealed Secrets (Recommended)

```bash
# Install Sealed Secrets
kubectl apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.24.0/controller.yaml

# Create a sealed secret
echo -n "real-value" | kubectl create secret generic kube-seer-secrets \
  --from-file=ELASTICSEARCH_PASSWORD=/dev/stdin \
  --dry-run=client -o yaml | kubeseal -o yaml > k8s/sealed-secrets.yaml
```

### 2. External Secrets Operator

```yaml
# With HashiCorp Vault, AWS Secrets Manager, etc.
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: kube-seer-secrets
spec:
  secretStoreRef:
    name: vault-backend
    kind: SecretStore
```

### 3. SOPS

```bash
# Encrypt secrets files
sops -e k8s/secrets.yaml > k8s/secrets.enc.yaml
```

## Security Audit

### Check for committed secrets

```bash
# Search for suspicious patterns
git log --all --full-history -- .env
git log --all --full-history -S "password"
git log --all --full-history -S "token"

# Scan with tooling
pip install detect-secrets
detect-secrets scan --all-files
```

### Clean history if necessary

```bash
# Remove a file from the entire history
git filter-branch --tree-filter 'rm -f .env' HEAD
git push --force-with-lease
```

## In Case of a Leak

1. **Immediately rotate** all exposed passwords / tokens
2. **Revoke** compromised credentials
3. **Clean** the Git history if necessary
4. **Audit** logs to detect malicious usage

## Pre-Commit Checklist

- [ ] No hardcoded passwords in code
- [ ] `.env*` files in `.gitignore`
- [ ] Examples use fake/placeholder values
- [ ] Documentation mentions security
- [ ] Tests do not use real credentials

## Safe Development Variables

```bash
# For local testing, use fake values
ELASTICSEARCH_URL=http://localhost:9200
ELASTICSEARCH_PASSWORD=dev-password-not-real
SLACK_WEBHOOK=http://localhost:3000/fake-webhook
```

## Security Contact

If you discover a security issue:
- Open a **confidential issue**
- Do not expose details publicly
- Propose a fix in the same issue
