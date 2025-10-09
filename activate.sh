#!/bin/bash
# Script d'activation de l'environnement de développement

if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
    echo "✅ Environnement virtuel activé"
    echo "🐍 Python: $(python --version)"
    echo "📦 Pip: $(pip --version | cut -d' ' -f1,2)"
    echo ""
    echo "💡 Commandes utiles:"
    echo "  make help           # Voir toutes les commandes"
    echo "  make test-unit      # Tests unitaires"
    echo "  make format         # Formater le code"
    echo "  make deploy         # Déployer avec Kind"
    echo ""
else
    echo "❌ Environnement virtuel non trouvé"
    echo "💡 Lancez: ./setup.sh"
fi
