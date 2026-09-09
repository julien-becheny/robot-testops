"""
Routes API pour la gestion de la configuration.

Endpoints :
- GET /config-vars : Récupère toutes les variables de configuration
- POST /config-vars : Met à jour une variable de configuration
"""

import subprocess

from flask import Blueprint, jsonify, request

from core import config, environments
from core.config import MASKED_CONFIG_VALUE
from core.logging_config import get_logger
from core.paths import paths

config_bp = Blueprint('config', __name__)
logger = get_logger(__name__)


@config_bp.route('/environments', methods=['GET'])
def get_environments():
    """Retourne les environnements declares et celui actuellement selectionne.

    Returns:
        Une reponse JSON {environments: [...], active: str | None}.
    """
    try:
        declared = environments.list_environments()
        active = environments.active_environment()
    except ValueError as exc:
        logger.error("Referentiel des environnements invalide : %s", exc)
        return jsonify({'error': str(exc)}), 500

    return jsonify({'environments': declared, 'active': active})


@config_bp.route('/config-vars', methods=['GET'])
def get_config_vars():
    """Retourne les variables de configuration avec les secrets masqués.

    Returns:
        Une réponse JSON plate compatible avec les consommateurs existants.
    """
    config.reload()
    return jsonify(config.get_public_all())


@config_bp.route('/config-vars', methods=['POST'])
def update_config_var():
    """Met à jour une variable connue sans jamais renvoyer un secret brut.

    Body:
        {
            'key': str,
            'value': any
        }
    
    Returns:
        Une réponse JSON avec la valeur publique après sauvegarde.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Corps JSON invalide'}), 400

    key = data.get('key')
    if not isinstance(key, str) or not key:
        return jsonify({'error': 'Clé requise'}), 400
    if not config.is_editable_key(key):
        return jsonify({'error': 'Clé de configuration inconnue'}), 400
    if 'value' not in data:
        return jsonify({'error': 'Valeur requise'}), 400

    value = data['value']
    if config.is_sensitive_key(key) and value == MASKED_CONFIG_VALUE:
        return jsonify({'error': 'La valeur masquée ne peut pas être enregistrée'}), 400

    # Liste blanche : l'interface propose un menu, mais l'API peut être appelée
    # directement. Seul un environnement déclaré peut devenir la cible d'un run.
    if key == 'RF_ENVIRONMENT':
        try:
            declared = isinstance(value, str) and environments.get_environment(value) is not None
        except ValueError as exc:
            logger.error("Referentiel des environnements invalide : %s", exc)
            return jsonify({'error': str(exc)}), 500
        if not declared:
            return jsonify({'error': 'Environnement inconnu'}), 400

    if not config.set(key, value):
        logger.error("Échec de la sauvegarde de la variable %s", key)
        return jsonify({'error': 'Sauvegarde de la configuration impossible'}), 500

    return jsonify({
        'success': True,
        'message': f'{key} mis à jour',
        'key': key,
        'value': config.get_public_value(key),
    })


@config_bp.route('/git-info', methods=['GET'])
def get_git_info():
    """Retourne la branche Git courante du projet."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True, text=True, check=True,
            cwd=str(paths.PROJECT_ROOT)
        )
        return jsonify({'branch': result.stdout.strip()})
    except (OSError, subprocess.CalledProcessError):
        return jsonify({'branch': 'Unknown'})
