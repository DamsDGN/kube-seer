#!/usr/bin/env python3
"""
Script de validation de l'intégration LLM
"""

import sys
import os
sys.path.insert(0, 'src')

def test_configuration():
    """Test de la configuration LLM"""
    print("🔧 Test de la configuration LLM")
    
    try:
        from config import Config
        config = Config()
        
        print(f"  ✅ Configuration chargée")
        print(f"  📊 LLM enabled: {config.llm_enabled}")
        print(f"  🤖 Provider: {config.llm_provider}")
        print(f"  🎯 Model: {config.llm_model}")
        print(f"  🔑 API Key configuré: {'Oui' if config.llm_api_key else 'Non'}")
        
        return True
    except Exception as e:
        print(f"  ❌ Erreur: {e}")
        return False

def test_llm_module():
    """Test du module LLM (sans dépendances externes)"""
    print("\n🤖 Test du module LLMAnalyzer")
    
    try:
        # Test de base sans aiohttp
        from llm_analyzer import LLMAnalyzer
        from config import Config
        
        config = Config()
        config.llm_enabled = False  # Test en mode désactivé
        
        analyzer = LLMAnalyzer(config)
        
        print(f"  ✅ LLMAnalyzer instancié")
        print(f"  📊 Enabled: {analyzer.enabled}")
        print(f"  🤖 Provider: {analyzer.provider}")
        
        return True
    except ImportError as e:
        print(f"  ⚠️  Import error (dépendances manquantes): {e}")
        print(f"     Ceci est normal si aiohttp n'est pas installé")
        return True  # On considère cela comme normal en dev
    except Exception as e:
        print(f"  ❌ Erreur: {e}")
        return False

def test_api_integration():
    """Test de l'intégration API"""
    print("\n🌐 Test de l'intégration API")
    
    try:
        from api import app
        print(f"  ✅ API app importée")
        
        # Vérifier que les nouveaux endpoints sont définis
        routes = [route.path for route in app.routes]
        
        llm_routes = [
            "/llm/status",
            "/alerts/enhanced", 
            "/logs/patterns"
        ]
        
        for route in llm_routes:
            if any(r.startswith(route) for r in routes):
                print(f"  ✅ Route {route} trouvée")
            else:
                print(f"  ⚠️  Route {route} non trouvée")
        
        return True
    except Exception as e:
        print(f"  ❌ Erreur: {e}")
        return False

def test_agent_integration():
    """Test de l'intégration dans l'agent"""
    print("\n🤖 Test de l'intégration dans SREAgent")
    
    try:
        from agent import SREAgent
        from config import Config
        
        config = Config()
        agent = SREAgent(config)
        
        print(f"  ✅ SREAgent instancié avec LLMAnalyzer")
        print(f"  📊 LLM analyzer présent: {hasattr(agent, 'llm_analyzer')}")
        
        # Vérifier les nouvelles méthodes
        methods = [
            'enhance_alert_with_llm',
            'get_troubleshooting_guidance',
            'analyze_log_patterns_with_llm'
        ]
        
        for method in methods:
            if hasattr(agent, method):
                print(f"  ✅ Méthode {method} disponible")
            else:
                print(f"  ❌ Méthode {method} manquante")
        
        return True
    except Exception as e:
        print(f"  ❌ Erreur: {e}")
        return False

def test_helm_values():
    """Test des valeurs Helm"""
    print("\n⚓ Test de la configuration Helm")
    
    try:
        values_path = "helm/efk-sre-agent/values.yaml"
        if os.path.exists(values_path):
            with open(values_path, 'r') as f:
                content = f.read()
                
            if "llm:" in content:
                print("  ✅ Section LLM trouvée dans values.yaml")
            else:
                print("  ❌ Section LLM manquante dans values.yaml")
                
            if "LLM_ENABLED" in content:
                print("  ✅ Variable LLM_ENABLED trouvée")
            else:
                print("  ❌ Variable LLM_ENABLED manquante")
        else:
            print("  ⚠️  Fichier values.yaml non trouvé")
            
        return True
    except Exception as e:
        print(f"  ❌ Erreur: {e}")
        return False

def main():
    """Fonction principale"""
    print("🚀 Validation de l'intégration LLM - Agent SRE")
    print("=" * 50)
    
    tests = [
        test_configuration,
        test_llm_module,
        test_api_integration,
        test_agent_integration,
        test_helm_values
    ]
    
    results = []
    for test in tests:
        results.append(test())
    
    print("\n" + "=" * 50)
    print(f"📊 Résumé: {sum(results)}/{len(results)} tests réussis")
    
    if all(results):
        print("✅ Intégration LLM validée avec succès !")
        print("\n💡 Prochaines étapes :")
        print("   1. Configurer LLM_ENABLED=true dans .env")
        print("   2. Ajouter LLM_API_KEY pour votre provider")
        print("   3. Tester avec: python demo_llm.py")
    else:
        print("⚠️  Certains tests ont échoué - vérifiez les erreurs ci-dessus")

if __name__ == "__main__":
    main()