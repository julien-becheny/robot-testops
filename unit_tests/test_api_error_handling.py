"""Tests des erreurs HTTP publiques et du nettoyage des sessions incomplètes."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from api.app import app
from api.routes import execution_routes, tags_routes


@pytest.fixture
def client():
    """Retourne le client Flask utilisant le gestionnaire global d'erreurs."""
    return app.test_client()


def test_unexpected_route_error_returns_stable_message(
    monkeypatch: pytest.MonkeyPatch,
    client,
) -> None:
    """Une panne interne est journalisée sans révéler son texte au navigateur."""
    monkeypatch.setattr(
        tags_routes,
        'get_available_tags',
        Mock(side_effect=RuntimeError('détail interne sensible')),
    )

    response = client.get('/available-tags')

    assert response.status_code == 500
    assert response.get_json() == {'error': 'Erreur interne du serveur'}
    assert 'détail interne sensible' not in response.get_data(as_text=True)


def test_http_404_is_preserved_by_global_handler(client) -> None:
    """Le gestionnaire global ne transforme pas les erreurs HTTP normales."""
    response = client.get('/route-inexistante')

    assert response.status_code == 404


def test_thread_start_failure_removes_smoke_session(
    monkeypatch: pytest.MonkeyPatch,
    client,
) -> None:
    """Une session smoke n'est pas laissée pending si le thread ne démarre pas."""
    session = SimpleNamespace(session_id='session-failed')
    monkeypatch.setattr(
        execution_routes.registry,
        'create_session',
        Mock(return_value=session),
    )
    remove = Mock()
    monkeypatch.setattr(execution_routes.registry, 'remove', remove)
    thread = Mock()
    thread.start.side_effect = RuntimeError('thread indisponible')
    monkeypatch.setattr(execution_routes.threading, 'Thread', Mock(return_value=thread))

    response = client.post('/run-test', json={
        'workflow': 'smoke',
        'browser': 'chromium',
        'viewport': '1920x1080',
    })

    assert response.status_code == 500
    assert response.get_json() == {'error': 'Erreur interne du serveur'}
    remove.assert_called_once_with('session-failed')


def test_thread_start_failure_removes_tag_session(
    monkeypatch: pytest.MonkeyPatch,
    client,
) -> None:
    """Une session par tags est également retirée si son thread échoue."""
    session = SimpleNamespace(session_id='session-tags-failed')
    monkeypatch.setattr(
        tags_routes,
        'get_available_tags',
        Mock(return_value={'tags': [{'name': 'smoke'}]}),
    )
    monkeypatch.setattr(
        tags_routes,
        'get_matching_tests',
        Mock(return_value=[{'name': 'Test A'}]),
    )
    monkeypatch.setattr(tags_routes.registry, 'create_session', Mock(return_value=session))
    remove = Mock()
    monkeypatch.setattr(tags_routes.registry, 'remove', remove)
    thread = Mock()
    thread.start.side_effect = RuntimeError('thread indisponible')
    monkeypatch.setattr(tags_routes.threading, 'Thread', Mock(return_value=thread))

    response = client.post('/run-by-tags', json={
        'include_tags': ['smoke'],
        'exclude_tags': [],
        'rerun_failed': False,
        'is_random': False,
        'nb_selection': 0,
        'browser': 'chromium',
        'viewport': '1920x1080',
    })

    assert response.status_code == 500
    assert response.get_json() == {'error': 'Erreur interne du serveur'}
    remove.assert_called_once_with('session-tags-failed')


def test_stop_signal_write_error_does_not_expose_path(
    monkeypatch: pytest.MonkeyPatch,
    client,
) -> None:
    """Une erreur disque retourne un message public sans chemin interne."""
    stop_path = Mock()
    stop_path.write_text.side_effect = OSError('chemin secret du poste')
    monkeypatch.setattr(
        execution_routes.registry,
        'stop_signal_path',
        Mock(return_value=stop_path),
    )

    response = client.post('/stop-test', json={'session_id': 'session-1'})

    assert response.status_code == 500
    assert response.get_json() == {'error': 'Erreur interne du serveur'}
    assert 'chemin secret du poste' not in response.get_data(as_text=True)


def test_log_payload_type_error_returns_400(client) -> None:
    """Une erreur de contrat reste une réponse 400 et non une panne interne."""
    response = client.post('/log', json={'message': ['pas', 'une', 'chaîne']})

    assert response.status_code == 400
    assert response.get_json() == {'error': 'message doit être une chaîne'}
