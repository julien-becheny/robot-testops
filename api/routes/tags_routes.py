"""
Routes API pour la gestion des tags et l'exécution filtrée.

Endpoints :
- GET /available-tags : Liste tous les tags disponibles avec compteurs
- POST /matching-tests : Retourne les tests matchant les tags sélectionnés
- POST /run-by-tags : Lance l'exécution filtrée par tags
"""

import threading

from flask import Blueprint, jsonify, request

from api.validation import (
    RequestValidationError,
    normalize_tag_filters,
    require_json_object,
    validate_boolean,
    validate_run_target,
    validate_selection_count,
)
from core import config
from core.session_registry import registry
from services.tags.manager import get_available_tags, get_matching_tests

tags_bp = Blueprint('tags', __name__)


def _available_tag_names() -> list[str]:
    """Retourne les noms canoniques du catalogue de tags actuellement résolu."""
    return [tag['name'] for tag in get_available_tags()['tags']]


def _validated_tag_filters(data: dict) -> tuple[list[str], list[str]]:
    """Valide les deux filtres de tags contre le catalogue Robot actuel."""
    return normalize_tag_filters(
        data.get('include_tags', []),
        data.get('exclude_tags', []),
        _available_tag_names(),
    )


@tags_bp.route('/available-tags', methods=['GET'])
def available_tags():
    """Retourne tous les tags disponibles avec compteurs et tests associés."""
    return jsonify(get_available_tags())


@tags_bp.route('/matching-tests', methods=['POST'])
def matching_tests():
    """
    Retourne les tests matchant les critères de tags.
    
    Body:
        {
            'include_tags': list,
            'exclude_tags': list
        }
    """
    try:
        data = require_json_object(request.get_json(silent=True))
        include_tags, exclude_tags = _validated_tag_filters(data)
    except RequestValidationError as exc:
        return jsonify({'error': str(exc)}), 400

    tests = get_matching_tests(include_tags, exclude_tags)
    return jsonify({'tests': tests, 'count': len(tests)})


@tags_bp.route('/run-by-tags', methods=['POST'])
def run_by_tags():
    """
    Lance l'exécution filtrée par tags.
    
    Body:
        {
            'include_tags': list,
            'exclude_tags': list,
            'rerun_failed': bool,
            'is_random': bool,
            'nb_selection': int
        }
    """
    try:
        data = require_json_object(request.get_json(silent=True))
        include_tags, exclude_tags = _validated_tag_filters(data)
        rerun_failed = validate_boolean(data.get('rerun_failed', False), 'rerun_failed')
        is_random = validate_boolean(data.get('is_random', False), 'is_random')
        nb_selection = validate_selection_count(data.get('nb_selection', 0), is_random)

        if not include_tags and not is_random:
            raise RequestValidationError("Au moins un tag d'inclusion est requis")

        browser, _viewport, device = validate_run_target(
            data,
            config.get('RF_BROWSER', 'chromium'),
            config.get('RF_VIEWPORT', '1920x1080'),
        )
        matching = get_matching_tests(include_tags, exclude_tags)
        matching_count = len(matching)
        if matching_count == 0:
            raise RequestValidationError("Aucun test ne correspond aux filtres")
        if is_random and nb_selection > matching_count:
            raise RequestValidationError(
                "nb_selection dépasse le nombre de tests correspondants"
            )
    except RequestValidationError as exc:
        return jsonify({'error': str(exc)}), 400

    workflow = 'randomized' if is_random else 'tag_filtered'

    from services.execution.orchestrator import run_workflow

    session = registry.create_session(browser=browser, workflow=workflow)

    thread = threading.Thread(
        target=run_workflow,
        args=(workflow,),
        kwargs={
            'include_tags': include_tags,
            'exclude_tags': exclude_tags,
            'rerun_failed': rerun_failed,
            'is_random': is_random,
            'nb_selection': nb_selection,
            'session_id': session.session_id,
            'browser': browser,
            'device': device,
        },
        daemon=True
    )
    try:
        thread.start()
    except (OSError, RuntimeError):
        registry.remove(session.session_id)
        raise

    return jsonify({
        'status': 'started',
        'session_id': session.session_id,
        'message': (
            f'Exécution {"aléatoire" if is_random else "filtrée"} '
            f'lancée avec tags: {", ".join(include_tags)}'
        ),
        'matching_tests': matching_count,
        'rerun_failed': rerun_failed,
        'is_random': is_random
    })
