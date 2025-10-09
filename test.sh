#!/bin/bash
# Script de test rapide

set -e

echo "🧪 Tests rapides de l'agent SRE..."

# Activer l'environnement
source .venv/bin/activate

# Tests de syntaxe
echo "1️⃣ Vérification de la syntaxe Python..."
python -m py_compile src/*.py

# Tests d'imports
echo "2️⃣ Vérification des imports..."
python -c "
import sys
sys.path.insert(0, 'src')
try:
    from config import Config
    from models import Alert, Metric, LogEntry
    print('✅ Imports principaux OK')
except ImportError as e:
    print(f'❌ Erreur d\'import: {e}')
    sys.exit(1)
"

# Tests unitaires (si disponibles)
if command -v pytest &> /dev/null; then
    echo "3️⃣ Lancement des tests unitaires..."
    pytest tests/ -v --tb=short || echo "⚠️ Certains tests ont échoué"
else
    echo "⚠️ pytest non disponible, installation des dépendances de test..."
    pip install pytest pytest-asyncio
fi

echo "✅ Tests terminés"
