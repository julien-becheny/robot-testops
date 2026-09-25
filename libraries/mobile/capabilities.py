"""Capabilities Appium (Android + iOS) - SOURCE UNIQUE, lue via ``core.config``.

Toutes les valeurs sensibles (chemin app,
package, UDID, bundle id) proviennent de ``variables_config.json`` - rien de hardcodé.

Importé côté Robot via ::

    Variables  ../../mobile/capabilities.py

Expose : ``APPIUM_URL``, ``ANDROID_CAPABILITIES``, ``IOS_CAPABILITIES``,
``MOBILE_CAPABILITIES`` (le dict de la plateforme courante ``RF_MOBILE_PLATFORM``).
"""

# Standard library
import sys
from pathlib import Path

# Bootstrap : garantir que la racine projet est sur le sys.path pour importer core
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Local/projet
from core import config

APPIUM_URL = config.get("RF_APPIUM_URL", "http://127.0.0.1:4723")  # url-ok: serveur Appium local, pas la cible du test


def _clean(caps: dict) -> dict:
    """Retire les capabilities non definies (None) pour ne pas les envoyer a Appium."""
    return {key: value for key, value in caps.items() if value is not None}


ANDROID_CAPABILITIES = _clean({
    "platformName": "Android",
    "appium:automationName": "UiAutomator2",
    "appium:app": config.get("RF_ANDROID_APP"),
    "appium:appPackage": config.get("RF_ANDROID_PACKAGE"),
    "appium:appActivity": config.get("RF_ANDROID_ACTIVITY"),
    "appium:autoGrantPermissions": True,
    "appium:noReset": True,
    "appium:newCommandTimeout": 300,
})

IOS_CAPABILITIES = _clean({
    "platformName": "iOS",
    "appium:automationName": "XCUITest",
    "appium:udid": config.get("RF_IOS_UDID"),
    "appium:bundleId": config.get("RF_IOS_BUNDLE_ID"),
    "appium:autoAcceptAlerts": True,
    "appium:noReset": True,
    "appium:newCommandTimeout": 300,
})

# Web sur mobile réel : pilote le navigateur du device (Chrome sur Android).
# Meme site que le web desktop -> memes locators ; seul le moteur change.
WEB_ANDROID_CAPABILITIES = _clean({
    "platformName": "Android",
    "appium:automationName": "UiAutomator2",
    "browserName": "Chrome",
    "appium:chromedriverAutodownload": True,
    "appium:newCommandTimeout": 300,
})


def _selected_capabilities() -> dict:
    """Retourne le dict de capabilities de la plateforme courante (défaut : Android)."""
    platform = (config.get("RF_MOBILE_PLATFORM") or "Android").strip().lower()
    return IOS_CAPABILITIES if platform in ("ios", "iphone", "ipad") else ANDROID_CAPABILITIES


MOBILE_CAPABILITIES = _selected_capabilities()
