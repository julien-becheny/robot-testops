"""
Routes API mobile (Appium).

- GET /mobile-preflight : etat de la chaine mobile (serveur Appium, driver, appareil)
  pour la plateforme courante (RF_MOBILE_PLATFORM). Consomme par l'UI (badge Reglages).
"""

from flask import Blueprint, jsonify

from services.mobile.appium_server import (
    start as appium_start,
)
from services.mobile.appium_server import (
    stop as appium_stop,
)
from services.mobile.preflight import check_mobile_env

mobile_bp = Blueprint('mobile', __name__)


@mobile_bp.route('/mobile-preflight', methods=['GET'])
def mobile_preflight():
    """Etat de la chaine mobile pour la plateforme courante."""
    return jsonify(check_mobile_env())


@mobile_bp.route('/mobile/appium/start', methods=['POST'])
def mobile_appium_start():
    """Demarre le serveur Appium (a la demande). Non bloquant."""
    return jsonify(appium_start())


@mobile_bp.route('/mobile/appium/stop', methods=['POST'])
def mobile_appium_stop():
    """Arrete le serveur Appium lance par TestOps."""
    return jsonify(appium_stop())
