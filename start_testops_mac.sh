#!/bin/bash
# Script de démarrage TestOps pour macOS

echo "================================================================================"
echo "                    DÉMARRAGE DE TESTOPS"
echo "                 Test Automation Control Panel"
echo "================================================================================"

# osascript et open n'existent que sous macOS : ailleurs le script n'ouvrirait aucun service.
if [ "$(uname -s)" != "Darwin" ]; then
    echo "❌ Ce script pilote Terminal.app via osascript : il ne fonctionne que sous macOS."
    echo "   Sous Linux : ./start_testops_linux.sh"
    echo "   Sous Windows : start_testops_windows.bat"
    exit 1
fi

if ! command -v uv &>/dev/null; then
    echo "❌ uv est introuvable dans le PATH - voir la section Démarrage du README."
    exit 1
fi

# Obtenir le répertoire de travail courant
WORK_DIR=$(pwd)
echo "📂 Répertoire de travail: $WORK_DIR"

# Démarrer Flask dans un terminal dédié
echo "🌐 Démarrage du serveur Flask..."
# L'activation ne sert pas au lancement (uv s'en charge) mais à la RELANCE manuelle :
# après un Ctrl+C, `python api/app.py` vise alors le bon interpréteur, et le prompt le montre.
osascript -e "
tell application \"Terminal\"
    do script \"cd '$WORK_DIR' && echo '🌐 SERVEUR FLASK - TestOps' && echo '══════════════════════════════════════════════════════════════════════' && source .venv/bin/activate ; uv run python api/app.py\"
    set custom title of front window to \"🌐 TestOps - Flask Server\"
end tell
"

# Démarrer React dans un terminal dédié
echo "⚛️ Démarrage de l'interface React..."
osascript -e "
tell application \"Terminal\"
    do script \"cd '$WORK_DIR/testops' && echo '⚛️ INTERFACE REACT - TestOps' && echo '═══════════════════════════════════════════════════════════════════════════' && export BROWSER=none && npm start\"
    set custom title of front window to \"⚛️ TestOps - React App\"
end tell
"

# Attendre avant d'ouvrir le navigateur
echo "⏳ Initialisation des services en cours..."
sleep 10

# Ouvrir l'interface dans le navigateur
echo "🌐 Ouverture de l'interface utilisateur..."
open "http://localhost:3000" 2>/dev/null || \
open -a "Google Chrome" "http://localhost:3000" 2>/dev/null || \
open -a "Safari" "http://localhost:3000" 2>/dev/null

echo ""
echo "================================================================================"
echo "                        TESTOPS DÉMARRÉ"
echo "================================================================================"
echo "Utilisez ces URL pour accéder aux services:"
echo "  • Interface utilisateur : http://localhost:3000"
echo "  • API Flask             : http://localhost:5001"
echo ""
echo "📋 Pour arrêter tous les services, fermez les terminaux ouverts"
echo "================================================================================"
