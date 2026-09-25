"""Helpers pour les test_objects mobile multi-plateforme (Android + iOS).

Version allégée d'un pattern `loc()` multi-plateforme : on ne garde que le routage
Android / iOS (pas de Windows, inutile ici).

La plateforme courante est lue via ``core.config`` (clé ``RF_MOBILE_PLATFORM`` :
``Android`` ou ``iOS``). Défaut : Android.

Usage dans un ``to_*.py`` (import sibling, voir to_login.py) ::

    from to_utils import loc

    TO_LOGIN = {
        # Locator identique Android / iOS (accessibility_id par défaut)
        "BTN_LOGIN": loc("login_button"),
        # Locators différents par plateforme
        "FLD_USERNAME": loc(
            android="accessibility_id=username_field",
            ios="//XCUIElementTypeTextField[@name='username']",
        ),
    }
"""

# Standard library
import sys
from pathlib import Path

# Bootstrap : garantir que la racine projet est sur le sys.path pour importer core
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Local/projet
from core import config


def _get_platform() -> str:
    """Retourne 'ios' ou 'android' selon RF_MOBILE_PLATFORM (défaut : android)."""
    value = (config.get("RF_MOBILE_PLATFORM") or "Android").strip().lower()
    return "ios" if value in ("ios", "iphone", "ipad") else "android"


def loc(element_id: str | None = None, *, android: str | None = None,
    ios: str | None = None) -> str:
    """Route un locator selon la plateforme mobile courante.

    - ``loc("id")`` : identifiant commun aux deux OS -> ``accessibility_id=id``.
    - ``loc(android=..., ios=...)`` : un locator dédié par plateforme.
    - ``loc("id", ios="//...")`` : id commun avec surcharge iOS.
    """
    platform = _get_platform()
    specific = ios if platform == "ios" else android
    if specific is not None:
        return specific
    if element_id is not None:
        return f"accessibility_id={element_id}"
    raise ValueError(
        f"loc() requiert un locator pour la plateforme '{platform}' ou un element_id commun"
    )
