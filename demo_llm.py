#!/usr/bin/env python3
"""
Script de démonstration des fonctionnalités LLM de l'agent SRE
"""

import asyncio
import sys
import os
from pathlib import Path

# Ajouter le répertoire src au path Python
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from config import Config
from llm_analyzer import LLMAnalyzer
from models import Alert, LogEntry
from datetime import datetime, UTC


async def demo_llm_features():
    """Démonstration des fonctionnalités LLM"""
    
    print("🤖 Démonstration des fonctionnalités LLM de l'Agent SRE")
    print("=" * 60)
    
    # Configuration
    config = Config()
    
    if not config.llm_enabled:
        print("❌ LLM non activé. Configurez les variables d'environnement :")
        print("   LLM_ENABLED=true")
        print("   LLM_PROVIDER=openai")
        print("   LLM_API_KEY=your-api-key")
        print("\nOu utilisez Ollama en local :")
        print("   LLM_ENABLED=true")
        print("   LLM_PROVIDER=ollama") 
        print("   LLM_BASE_URL=http://localhost:11434")
        return
    
    analyzer = LLMAnalyzer(config)
    
    print(f"✅ LLM activé : {config.llm_provider} ({config.llm_model})")
    print()
    
    # Créer des exemples d'alertes et de logs
    sample_alert = Alert(
        type="resource_usage",
        severity="critical",
        message="CPU usage critical: 95% on pod web-app-123 in namespace production",
        timestamp=datetime.now(UTC),
        metadata={
            "pod_name": "web-app-123",
            "namespace": "production",
            "cpu_percent": 95,
            "memory_percent": 78
        }
    )
    
    sample_logs = [
        LogEntry(
            timestamp=datetime.now(UTC),
            pod_name="web-app-123",
            message="java.lang.OutOfMemoryError: Java heap space at com.example.Service.processRequest(Service.java:42)",
            level="ERROR"
        ),
        LogEntry(
            timestamp=datetime.now(UTC),
            pod_name="web-app-123",
            message="Connection timeout to database server db-primary:5432",
            level="ERROR"
        ),
        LogEntry(
            timestamp=datetime.now(UTC),
            pod_name="api-service-456",
            message="HTTP 500 Internal Server Error: Failed to process user request",
            level="ERROR"
        )
    ]
    
    print("📋 Données d'exemple créées")
    print(f"   Alerte : {sample_alert.message}")
    print(f"   Logs : {len(sample_logs)} entrées d'erreur")
    print()
    
    # Test 1: Amélioration d'alerte
    print("🔍 Test 1 : Amélioration de l'interprétation d'alerte")
    print("-" * 50)
    
    try:
        context = {"recent_cpu": 95, "recent_memory": 78}
        enhanced_alert = await analyzer.enhance_alert_interpretation(sample_alert, context)
        
        if enhanced_alert["enhanced"]:
            print("✅ Analyse LLM réussie !")
            print(f"Interprétation : {enhanced_alert.get('interpretation', 'N/A')}")
            print(f"Recommandations : {enhanced_alert.get('recommendations', [])}")
        else:
            print(f"❌ Erreur : {enhanced_alert.get('error', 'Analyse non disponible')}")
            
    except Exception as e:
        print(f"❌ Erreur lors de l'amélioration d'alerte : {e}")
    
    print()
    
    # Test 2: Analyse des patterns de logs
    print("📜 Test 2 : Analyse des patterns dans les logs")
    print("-" * 50)
    
    try:
        log_analysis = await analyzer.analyze_log_patterns(sample_logs)
        
        if log_analysis["enhanced"]:
            print("✅ Analyse des logs réussie !")
            print(f"Résumé : {log_analysis.get('summary', 'N/A')}")
            print(f"Patterns détectés : {len(log_analysis.get('patterns', []))}")
            
            for i, pattern in enumerate(log_analysis.get('patterns', [])[:2]):
                print(f"  Pattern {i+1}: {pattern.get('description', 'N/A')}")
        else:
            print(f"❌ Erreur : {log_analysis.get('error', 'Analyse non disponible')}")
            
    except Exception as e:
        print(f"❌ Erreur lors de l'analyse des logs : {e}")
    
    print()
    
    # Test 3: Guide de dépannage
    print("🛠️  Test 3 : Génération de guide de dépannage")
    print("-" * 50)
    
    try:
        troubleshooting = await analyzer.provide_troubleshooting_guidance(
            sample_alert, 
            recent_logs=sample_logs
        )
        
        if troubleshooting["enhanced"]:
            print("✅ Guide de dépannage généré !")
            
            immediate_actions = troubleshooting.get('immediate_actions', [])
            if immediate_actions:
                print("Actions immédiates :")
                for action in immediate_actions[:3]:
                    print(f"  • {action}")
            
            common_solutions = troubleshooting.get('common_solutions', [])
            if common_solutions:
                print("Solutions courantes :")
                for solution in common_solutions[:2]:
                    print(f"  • {solution.get('problem', 'N/A')} → {solution.get('solution', 'N/A')}")
        else:
            print(f"❌ Erreur : {troubleshooting.get('error', 'Guide non disponible')}")
            
    except Exception as e:
        print(f"❌ Erreur lors de la génération du guide : {e}")
    
    print()
    print("🎯 Démonstration terminée !")
    print()
    print("💡 Pour tester l'API REST avec ces fonctionnalités :")
    print("   python demo.py")
    print("   curl http://localhost:8080/llm/status")
    print("   curl http://localhost:8080/alerts/enhanced")


async def demo_api_examples():
    """Affiche des exemples d'utilisation de l'API"""
    print("🌐 Exemples d'utilisation de l'API LLM")
    print("=" * 40)
    print()
    
    examples = [
        ("Statut LLM", "curl http://localhost:8080/llm/status"),
        ("Alertes enrichies", "curl http://localhost:8080/alerts/enhanced?limit=5"),
        ("Patterns de logs", "curl http://localhost:8080/logs/patterns?limit=20"),
        ("Guide dépannage", "curl -X POST http://localhost:8080/alerts/{alert_id}/troubleshoot"),
        ("Améliorer alerte", "curl -X POST http://localhost:8080/alerts/{alert_id}/enhance"),
    ]
    
    for name, command in examples:
        print(f"📋 {name}")
        print(f"   {command}")
        print()


def main():
    """Point d'entrée principal"""
    print("🚀 Agent SRE - Démonstration LLM")
    print()
    
    # Vérifier les variables d'environnement de base
    if len(sys.argv) > 1 and sys.argv[1] == "--api-examples":
        asyncio.run(demo_api_examples())
        return
    
    # Test de configuration
    try:
        config = Config()
        print(f"Configuration chargée : LLM {'activé' if config.llm_enabled else 'désactivé'}")
    except Exception as e:
        print(f"❌ Erreur de configuration : {e}")
        print("\n💡 Vérifiez vos variables d'environnement dans .env")
        return
    
    # Lancer la démonstration
    try:
        asyncio.run(demo_llm_features())
    except KeyboardInterrupt:
        print("\n🛑 Démonstration interrompue")
    except Exception as e:
        print(f"\n❌ Erreur lors de la démonstration : {e}")


if __name__ == "__main__":
    main()