# 🤖 Intégration LLM - Agent SRE

Cette fonctionnalité optionnelle améliore l'agent SRE avec des capacités d'analyse avancées utilisant des modèles de langage (LLM).

## 🎯 Objectifs

L'intégration LLM permet de :
- **Interpréter** les événements avec un contexte expert SRE
- **Recommander** des actions spécifiques pour chaque incident
- **Générer** des guides de dépannage détaillés
- **Analyser** les patterns complexes dans les logs
- **Contextualiser** les alertes avec des explications claires

## 🚀 Fonctionnalités

### 1. Amélioration d'Alertes
Transforme les alertes techniques en analyses contextuelles :

**Avant :**
```
CPU usage critical: 95% on pod web-app-123
```

**Après (avec LLM) :**
```json
{
  "interpretation": "Le pod web-app-123 subit une charge CPU critique qui peut entraîner une dégradation des performances et des timeouts pour les utilisateurs",
  "root_cause": "Probable pic de trafic ou fuite mémoire causant une surconsommation CPU",
  "impact": "Les utilisateurs peuvent expérimenter des réponses lentes ou des erreurs 503",
  "recommendations": [
    "Vérifier les métriques de trafic sur les 30 dernières minutes",
    "Examiner les logs d'application pour des patterns d'erreur",
    "Considérer un scaling horizontal immédiat"
  ]
}
```

### 2. Guides de Dépannage
Génère des instructions étape par étape pour résoudre les incidents :

```json
{
  "immediate_actions": [
    "Vérifier l'état du pod avec kubectl get pod web-app-123 -o wide",
    "Examiner les logs récents avec kubectl logs web-app-123 --tail=100"
  ],
  "diagnostic_commands": [
    {
      "command": "kubectl top pod web-app-123",
      "purpose": "Vérifier la consommation actuelle des ressources"
    }
  ],
  "common_solutions": [
    {
      "problem": "Fuite mémoire Java",
      "solution": "Redémarrer le pod et ajuster les paramètres JVM"
    }
  ]
}
```

### 3. Analyse de Patterns
Détecte des patterns complexes dans les logs que les règles traditionnelles pourraient manquer :

```json
{
  "patterns": [
    {
      "type": "error",
      "description": "Séquence d'erreurs de connexion base de données suivies d'OOM",
      "frequency": "Répétée 3 fois en 10 minutes",
      "severity": "HIGH",
      "affected_pods": ["web-app-123", "api-service-456"]
    }
  ],
  "summary": "Problème de cascade d'erreurs suggérant un problème de pool de connexions",
  "trends": "Augmentation progressive des erreurs depuis 15 minutes"
}
```

## 🔧 Configuration

### Providers Supportés

#### OpenAI GPT
```bash
LLM_ENABLED=true
LLM_PROVIDER=openai
LLM_API_KEY=sk-your-api-key-here
LLM_MODEL=gpt-3.5-turbo  # ou gpt-4
```

#### Anthropic Claude
```bash
LLM_ENABLED=true
LLM_PROVIDER=anthropic
LLM_API_KEY=your-anthropic-key
LLM_MODEL=claude-3-sonnet-20240229
```

#### Ollama (Local)
```bash
LLM_ENABLED=true
LLM_PROVIDER=ollama
LLM_MODEL=llama2  # ou codellama, mistral, etc.
LLM_BASE_URL=http://localhost:11434
```

### Paramètres Avancés
```bash
LLM_MAX_TOKENS=1000      # Limite de tokens par réponse
LLM_TEMPERATURE=0.1      # Créativité (0.0 = déterministe, 1.0 = créatif)
```

## 🛠️ Installation

### 1. Avec OpenAI
```bash
# 1. Obtenir une clé API sur https://platform.openai.com
# 2. Configurer l'environnement
echo "LLM_ENABLED=true" >> .env
echo "LLM_PROVIDER=openai" >> .env
echo "LLM_API_KEY=sk-your-key" >> .env
echo "LLM_MODEL=gpt-3.5-turbo" >> .env

# 3. Redémarrer l'agent
make restart
```

### 2. Avec Ollama (Local)
```bash
# 1. Installer Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# 2. Démarrer Ollama et télécharger un modèle
ollama serve &
ollama pull llama2

# 3. Configurer l'agent
echo "LLM_ENABLED=true" >> .env
echo "LLM_PROVIDER=ollama" >> .env
echo "LLM_MODEL=llama2" >> .env
echo "LLM_BASE_URL=http://localhost:11434" >> .env

# 4. Redémarrer l'agent
make restart
```

### 3. Avec Helm (Kubernetes)
```bash
# Créer un secret avec la clé API
kubectl create secret generic llm-secret \
  --from-literal=LLM_API_KEY=your-api-key \
  -n monitoring

# Déployer avec LLM activé
helm upgrade --install efk-sre-agent ./helm/efk-sre-agent/ \
  --set llm.enabled=true \
  --set llm.provider=openai \
  --set llm.model=gpt-3.5-turbo \
  --set llm.apiKey=your-api-key \
  -n monitoring
```

## 📊 API Endpoints

### Statut LLM
```bash
GET /llm/status

Response:
{
  "enabled": true,
  "provider": "openai",
  "model": "gpt-3.5-turbo",
  "status": "active"
}
```

### Alertes Enrichies
```bash
GET /alerts/enhanced?limit=10

Response:
{
  "alerts": [
    {
      "alert": {
        "type": "resource_usage",
        "severity": "critical",
        "message": "CPU usage critical: 95%"
      },
      "enhanced_analysis": {
        "enhanced": true,
        "interpretation": "...",
        "recommendations": ["..."]
      }
    }
  ]
}
```

### Guide de Dépannage
```bash
POST /alerts/{alert_id}/troubleshoot

Response:
{
  "troubleshooting": {
    "enhanced": true,
    "immediate_actions": ["..."],
    "diagnostic_commands": [{"command": "...", "purpose": "..."}]
  }
}
```

## 🧪 Test et Démonstration

### Script de Démonstration
```bash
# Tester les fonctionnalités LLM
python demo_llm.py

# Exemples d'API
python demo_llm.py --api-examples
```

### Tests Unitaires
```bash
# Tests spécifiques LLM
pytest tests/test_llm_analyzer.py -v

# Tests avec mock (sans appels API réels)
pytest tests/test_llm_analyzer.py::TestLLMAnalyzer::test_enhance_alert_disabled -v
```

## 💰 Considérations de Coût

### OpenAI/Anthropic
- **Coût** : ~$0.001-0.03 par alerte analysée
- **Recommandation** : Utiliser pour la production avec alertes critiques
- **Optimisation** : Limiter `LLM_MAX_TOKENS` pour réduire les coûts

### Ollama (Local)
- **Coût** : Gratuit (ressources locales)
- **Recommandation** : Idéal pour développement/test
- **Ressources** : Nécessite 4-8GB RAM selon le modèle

## 🔒 Sécurité

### Bonnes Pratiques
1. **Clés API** : Stockées dans des secrets Kubernetes
2. **Données sensibles** : Anonymisation automatique dans les prompts
3. **Limitations** : Rate limiting pour éviter les abus
4. **Audit** : Logs des appels LLM pour traçabilité

### Configuration Sécurisée
```yaml
# values.yaml pour Helm
llm:
  enabled: true
  provider: openai
  apiKey: ""  # Défini via secret

# Secret séparé
apiVersion: v1
kind: Secret
metadata:
  name: llm-credentials
data:
  LLM_API_KEY: <base64-encoded-key>
```

## 🚨 Troubleshooting

### Problèmes Courants

#### "LLM non activé"
```bash
# Vérifier la configuration
echo $LLM_ENABLED
echo $LLM_PROVIDER

# Corriger si nécessaire
export LLM_ENABLED=true
export LLM_PROVIDER=openai
```

#### "API Key invalide"
```bash
# Tester la clé manuellement
curl -H "Authorization: Bearer $LLM_API_KEY" \
  https://api.openai.com/v1/models
```

#### "Ollama non accessible"
```bash
# Vérifier qu'Ollama fonctionne
curl http://localhost:11434/api/version

# Redémarrer si nécessaire
ollama serve
```

#### "Réponses vides du LLM"
- Vérifier `LLM_MAX_TOKENS` (minimum 500)
- Ajuster `LLM_TEMPERATURE` (0.1-0.3 recommandé)
- Examiner les logs de l'agent pour les erreurs

## 📈 Métriques et Monitoring

L'intégration LLM expose des métriques Prometheus :

```
# Nombre d'appels LLM
sre_agent_llm_calls_total{provider="openai",status="success"}

# Durée des appels LLM
sre_agent_llm_duration_seconds{provider="openai"}

# Erreurs LLM
sre_agent_llm_errors_total{provider="openai",error_type="api_limit"}
```

## 🗺️ Roadmap

### Version Actuelle (1.0)
- ✅ Support OpenAI, Anthropic, Ollama
- ✅ Amélioration d'alertes
- ✅ Guides de dépannage
- ✅ Analyse de patterns de logs

### Prochaines Versions
- 🔄 **1.1** : Mémorisation des analyses précédentes
- 🔄 **1.2** : Génération automatique de runbooks
- 🔄 **1.3** : Support d'autres providers (Azure OpenAI, Google PaLM)
- 🔄 **1.4** : Interface web pour visualiser les analyses LLM

## 🤝 Contribution

Pour contribuer aux fonctionnalités LLM :

1. **Tests** : Ajouter des tests pour nouveaux providers
2. **Prompts** : Améliorer les prompts pour de meilleures réponses
3. **Optimisation** : Réduire les coûts API par analyse
4. **Documentation** : Étendre les exemples d'utilisation

Voir [CONTRIBUTING.md](../CONTRIBUTING.md) pour plus de détails.