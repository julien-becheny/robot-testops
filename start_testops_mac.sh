#!/bin/bash
# Script de démarrage TestOps pour macOS

echo "================================================================================"
echo "                    DÉMARRAGE DE TESTOPS"
echo "                 Test Automation Control Panel"
echo "================================================================================"

# Obtenir le répertoire de travail courant
WORK_DIR=$(pwd)
echo "📂 Répertoire de travail: $WORK_DIR"

# Démarrer Flask dans un terminal dédié
echo "🌐 Démarrage du serveur Flask..."
osascript -e "
tell application \"Terminal\"
    do script \"cd '$WORK_DIR' && echo '🌐 SERVEUR FLASK - TestOps' && echo '═══════════════════════════════════════════════════════════════════════════' && source env/bin/activate && python api/app.py\"
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
