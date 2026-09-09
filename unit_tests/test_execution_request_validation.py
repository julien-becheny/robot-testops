"""Tests des payloads HTTP de lancement avant création de session ou de thread."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from api.app import app
from api.routes import execution_routes, tags_routes
from api.validation import normalize_tag_filters


@pytest.fixture
def client():
    """Retourne le client Flask sans démarrer de serveur réseau."""
    return app.test_client()


@pytest.fixture
def execution_starters(monkeypatch: pytest.MonkeyPatch):
    """Simule la création de session et de thread pour les routes d'exécution."""
    session = SimpleNamespace(session_id='session-1')
    create_session = Mock(return_value=session)
    thread_instance = Mock()
    thread_factory = Mock(return_value=thread_instance)
    monkeypatch.setattr(execution_routes.registry, 'create_session', create_session)
    monkeypatch.setattr(execution_routes.threading, 'Thread', thread_factory)
    return create_session, thread_factory, thread_instance


@pytest.fixture
def tag_starters(monkeypatch: pytest.MonkeyPatch):
    """Simule la découverte, la session et le thread de la route par tags."""
    session = SimpleNamespace(session_id='session-tags')
    create_session = Mock(return_value=session)
    thread_instance = Mock()
    thread_factory = Mock(return_value=thread_instance)
    monkeypatch.setattr(tags_routes.registry, 'create_session', create_session)
    monkeypatch.setattr(tags_routes.threading, 'Thread', thread_factory)
    monkeypatch.setattr(
        tags_routes,
        'get_available_tags',
        Mock(return_value={
            'tags': [
                {'name': 'smoke'},
                {'name': 'regression'},
                {'name': 'mobile'},
            ]
        }),
    )
    return create_session, thread_factory, thread_instance


@pytest.mark.parametrize('browser', ['chromium', 'firefox', 'webkit'])
@pytest.mark.parametrize('viewport', ['1920x1080', '768x1024', '375x812'])
def test_smoke_accepts_all_frontend_targets(
    client,
    execution_starters,
    browser: str,
    viewport: str,
) -> None:
    """Les neuf combinaisons réellement proposées dans le Header restent acceptées."""
    create_session, thread_factory, thread_instance = execution_starters

    response = client.post('/run-test', json={
        'workflow': 'smoke',
        'browser': browser,
        'viewport': viewport,
    })

    assert response.status_code == 200
    assert response.get_json()['session_id'] == 'session-1'
    create_session.assert_called_once_with(browser=browser, workflow='smoke')
    thread_factory.assert_called_once()
    thread_instance.start.assert_called_once_with()


@pytest.mark.parametrize('payload', [
    {'workflow': 'inconnu', 'browser': 'chromium', 'viewport': '1920x1080'},
    {'workflow': 'smoke', 'browser': 'edge', 'viewport': '1920x1080'},
    {'workflow': 'smoke', 'browser': 'chromium', 'viewport': '800x600'},
])
def test_invalid_smoke_payload_creates_no_session(
    client,
    execution_starters,
    payload: dict,
) -> None:
    """Une cible ou un workflow invalide est refusé avant les effets de bord."""
    create_session, thread_factory, _thread_instance = execution_starters

    response = client.post('/run-test', json=payload)

    assert response.status_code == 400
    create_session.assert_not_called()
    thread_factory.assert_not_called()


def test_tag_filters_use_catalog_without_arbitrary_count_limit() -> None:
    """Les tags sont canoniques et dédupliqués sans seuil numérique artificiel."""
    catalog = [f'tag-{index}' for index in range(150)]
    include, exclude = normalize_tag_filters(
        [*catalog, 'TAG-0'],
        [],
        catalog,
    )

    assert include == catalog
    assert exclude == []


@pytest.mark.parametrize('payload', [
    {'include_tags': 'smoke', 'exclude_tags': []},
    {'include_tags': ['inconnu'], 'exclude_tags': []},
    {'include_tags': ['smoke'], 'exclude_tags': ['SMOKE']},
    {'include_tags': ['smoke'], 'exclude_tags': [], 'rerun_failed': 1},
    {'include_tags': ['smoke'], 'exclude_tags': [], 'is_random': 'true'},
    {
        'include_tags': ['smoke'],
        'exclude_tags': [],
        'is_random': True,
        'nb_selection': -1,
    },
])
def test_invalid_tag_payload_creates_no_session(
    client,
    tag_starters,
    payload: dict,
) -> None:
    """Les types, tags et options invalides sont refusés avant le thread."""
    create_session, thread_factory, _thread_instance = tag_starters

    response = client.post('/run-by-tags', json={
        'rerun_failed': False,
        'is_random': False,
        'nb_selection': 0,
        'browser': 'chromium',
        'viewport': '1920x1080',
        **payload,
    })

    assert response.status_code == 400
    create_session.assert_not_called()
    thread_factory.assert_not_called()


def test_random_without_tags_keeps_select_all_behavior(
    monkeypatch: pytest.MonkeyPatch,
    client,
    tag_starters,
) -> None:
    """Le mode aléatoire sans filtre et nb_selection=0 conserve tous les tests."""
    create_session, thread_factory, thread_instance = tag_starters
    matching = Mock(return_value=[{'name': 'A'}, {'name': 'B'}])
    monkeypatch.setattr(tags_routes, 'get_matching_tests', matching)

    response = client.post('/run-by-tags', json={
        'include_tags': [],
        'exclude_tags': [],
        'rerun_failed': True,
        'is_random': True,
        'nb_selection': 0,
        'browser': 'firefox',
        'viewport': '768x1024',
    })

    assert response.status_code == 200
    assert response.get_json() == {
        'status': 'started',
        'session_id': 'session-tags',
        'message': 'Exécution aléatoire lancée avec tags: ',
        'matching_tests': 2,
        'rerun_failed': True,
        'is_random': True,
    }
    create_session.assert_called_once_with(browser='firefox', workflow='randomized')
    thread_factory.assert_called_once()
    thread_instance.start.assert_called_once_with()
    thread_kwargs = thread_factory.call_args.kwargs['kwargs']
    assert thread_kwargs['nb_selection'] == 0
    assert thread_kwargs['browser'] == 'firefox'
    assert thread_kwargs['device'] == 'tablet'


def test_random_selection_above_matching_count_creates_no_session(
    monkeypatch: pytest.MonkeyPatch,
    client,
    tag_starters,
) -> None:
    """Une sélection impossible est refusée au lieu d'être réduite silencieusement."""
    create_session, thread_factory, _thread_instance = tag_starters
    monkeypatch.setattr(tags_routes, 'get_matching_tests', Mock(return_value=[{'name': 'A'}]))

    response = client.post('/run-by-tags', json={
        'include_tags': ['smoke'],
        'exclude_tags': [],
        'rerun_failed': True,
        'is_random': True,
        'nb_selection': 2,
        'browser': 'chromium',
        'viewport': '1920x1080',
    })

    assert response.status_code == 400
    create_session.assert_not_called()
    thread_factory.assert_not_called()


def test_no_matching_test_creates_no_session(
    monkeypatch: pytest.MonkeyPatch,
    client,
    tag_starters,
) -> None:
    """Une exécution vide est refusée avant de créer une session fantôme."""
    create_session, thread_factory, _thread_instance = tag_starters
    monkeypatch.setattr(tags_routes, 'get_matching_tests', Mock(return_value=[]))

    response = client.post('/run-by-tags', json={
        'include_tags': ['smoke'],
        'exclude_tags': [],
        'rerun_failed': False,
        'is_random': False,
        'nb_selection': 0,
        'browser': 'chromium',
        'viewport': '1920x1080',
    })

    assert response.status_code == 400
    create_session.assert_not_called()
    thread_factory.assert_not_called()