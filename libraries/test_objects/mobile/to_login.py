"""Locators mobile de l'écran de connexion - EXEMPLE / TEMPLATE multi-OS.

Montre les 3 usages de ``loc()`` : id commun, locators dédiés par OS, id + surcharge.
Remplacer par les vrais locators de l'application mobile cible.
Importé côté Robot via ``Variables  ../../libraries/test_objects/mobile/to_login.py``.
"""

# Standard library
import sys
from pathlib import Path

# Bootstrap : rendre to_utils (même dossier) importable quel que soit le runner
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Local/projet
from to_utils import loc

TO_LOGIN = {  # PAGE "Connexion mobile"
    # Id d'accessibilité commun Android / iOS
    "BTN_LOGIN": loc("login_button"),
    # Locators dédiés par plateforme
    "FLD_USERNAME": loc(
        android="accessibility_id=username_field",
        ios="//XCUIElementTypeTextField[@name='username']",
    ),
    "FLD_PASSWORD": loc(
        android="accessibility_id=password_field",
        ios="//XCUIElementTypeSecureTextField[@name='password']",
    ),
    # Id commun avec surcharge iOS uniquement
    "MSG_ERROR": loc(
        "login_error",
        ios="//XCUIElementTypeStaticText[@name='login_error']",
    ),
}
