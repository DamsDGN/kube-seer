#!/usr/bin/env python3
"""
Script de démonstration pour tester l'agent SRE en mode standalone
"""

import asyncio
import sys
from pathlib import Path

# Ajouter le répertoire src au path Python
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from api import create_app
from config import Config
import uvicorn

async def main():
    """Démonstration de l'API en mode standalone"""
    print("🚀 Démonstration de l'agent IA SRE EFK")
    print("=" * 50)
    
    # Configuration pour le mode démo (sans Elasticsearch)
    config = Config()
    config.elasticsearch_url = "http://localhost:9999"  # URL factice pour éviter les erreurs
    
    # Créer l'application FastAPI
    app = create_app()
    
    print(f"🌐 Démarrage du serveur API sur http://localhost:8080")
    print("📋 Endpoints disponibles :")
    print("  - GET  /health          -> Status de l'agent")
    print("  - GET  /metrics         -> Métriques disponibles") 
    print("  - POST /analyze/metrics -> Analyse des métriques")
    print("  - POST /analyze/logs    -> Analyse des logs")
    print("  - GET  /alerts          -> Liste des alertes")
    print("  - GET  /models/status   -> Status des modèles ML")
    print("")
    print("💡 Testez avec : curl http://localhost:8080/health")
    print("🛑 Arrêt avec Ctrl+C")
    
    # Démarrer le serveur
    config_uvicorn = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=8080,
        log_level="info"
    )
    server = uvicorn.Server(config_uvicorn)
    await server.serve()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Démonstration arrêtée")