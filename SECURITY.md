# 🔒 Guide de Sécurité

## ⚠️ IMPORTANT : Informations Sensibles

Ce projet est **PUBLIC** sur GitHub. Ne jamais committer :

### ❌ À NE JAMAIS COMMITTER

- Mots de passe Elasticsearch
- Tokens d'API 
- Webhooks Slack avec tokens
- Credentials email
- Certificats/clés privées
- URLs internes avec credentials
- Fichiers `.env` avec vraies valeurs

### ✅ Protection en Place

Les fichiers suivants sont automatiquement ignorés :
- `.env`
- `.env.local` 
- `.env.production`
- `k8s/secrets.yaml`
- `k8s/local-*.yaml`
- `*.key`, `*.pem`, `*.crt`
- `secrets/`, `credentials/`

## 🛡️ Bonnes Pratiques

### 1. Variables d'Environnement

```bash
# Utiliser des variables d'environnement pour les secrets
export ELASTICSEARCH_PASSWORD="vraie-valeur-secrete"
export SLACK_WEBHOOK="https://hooks.slack.com/services/real/webhook/url"

# Ou un fichier .env local (non commité)
cp .env.example .env
# Éditer .env avec les vraies valeurs
```

### 2. Secrets Kubernetes

```bash
# Créer des secrets depuis des fichiers
kubectl create secret generic efk-sre-secrets \
  --from-env-file=.env \
  -n monitoring

# Ou individuellement
kubectl create secret generic efk-sre-secrets \
  --from-literal=ELASTICSEARCH_PASSWORD="vraie-valeur" \
  -n monitoring
```

### 3. Fichiers de Configuration

```bash
# Créer des configs locales (ignorées par git)
cp k8s/deployment.yaml k8s/local-deployment.yaml
# Modifier local-deployment.yaml avec des valeurs spécifiques
```

## 🔐 Gestion des Secrets en Production

### 1. Sealed Secrets (Recommandé)

```bash
# Installation de Sealed Secrets
kubectl apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.24.0/controller.yaml

# Créer un secret scellé
echo -n "vraie-valeur" | kubectl create secret generic efk-sre-secrets \
  --from-file=ELASTICSEARCH_PASSWORD=/dev/stdin \
  --dry-run=client -o yaml | kubeseal -o yaml > k8s/sealed-secrets.yaml
```

### 2. External Secrets Operator

```bash
# Avec HashiCorp Vault, AWS Secrets Manager, etc.
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: efk-sre-secrets
spec:
  secretStoreRef:
    name: vault-backend
    kind: SecretStore
```

### 3. SOPS (Secrets OPerationS)

```bash
# Chiffrer les fichiers de secrets
sops -e k8s/secrets.yaml > k8s/secrets.enc.yaml
```

## 🔍 Audit de Sécurité

### Vérifier qu'aucun secret n'est commité

```bash
# Rechercher des patterns suspects
git log --all --full-history -- .env
git log --all --full-history -S "password" 
git log --all --full-history -S "token"

# Scanner avec des outils
pip install detect-secrets
detect-secrets scan --all-files
```

### Nettoyer l'historique si nécessaire

```bash
# Supprimer un fichier de tout l'historique
git filter-branch --tree-filter 'rm -f .env' HEAD
git push --force-with-lease
```

## 🚨 En Cas de Fuite

1. **Changer immédiatement** tous les mots de passe/tokens exposés
2. **Révoquer** les accès compromis
3. **Nettoyer** l'historique Git si nécessaire
4. **Auditer** les logs pour détecter un usage malveillant

## 📋 Checklist Avant Commit

- [ ] Aucun mot de passe en dur dans le code
- [ ] Fichiers `.env*` dans `.gitignore`
- [ ] Exemples utilisent des valeurs factices
- [ ] Documentation mentionne la sécurité
- [ ] Tests n'utilisent pas de vraies credentials

## 🔧 Variables de Développement Sûres

```bash
# Pour les tests locaux, utiliser des valeurs factices
ELASTICSEARCH_URL=http://localhost:9200
ELASTICSEARCH_PASSWORD=dev-password-not-real
SLACK_WEBHOOK=http://localhost:3000/fake-webhook
```

## 📞 Contact Sécurité

En cas de problème de sécurité détecté :
- Créer une **issue confidentielle**
- Ne pas exposer les détails publiquement
- Proposer une solution dans la même issue