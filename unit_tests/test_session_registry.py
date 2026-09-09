"""Tests du registre thread-safe des sessions d'exécution."""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from core import session_registry
from core.session_registry import SessionRegistry


@pytest.fixture
def isolated_registry():
    """Isole le contenu du singleton pendant chaque test."""
    registry = SessionRegistry()
    with registry._lock:
        original_sessions = registry._sessions
        registry._sessions = {}
    yield registry
    with registry._lock:
        registry._sessions = original_sessions


def test_create_session_sets_defaults_and_start_time(isolated_registry) -> None:
    """Une nouvelle session possède un état pending et un horodatage."""
    session = isolated_registry.create_session(
        browser='firefox',
        workflow='smoke',
        started_by_ip='127.0.0.1',
    )

    assert session.browser == 'firefox'
    assert session.workflow == 'smoke'
    assert session.status == 'pending'
    assert session.started_at is not None
    assert session.started_by_ip == '127.0.0.1'


def test_short_id_collision_is_regenerated(
    monkeypatch: pytest.MonkeyPatch,
    isolated_registry,
) -> None:
    """Une collision sur huit caractères ne remplace jamais une session existante."""
    generated = iter([
        SimpleNamespace(hex='aaaaaaaa11111111'),
        SimpleNamespace(hex='aaaaaaaa22222222'),
        SimpleNamespace(hex='bbbbbbbb33333333'),
    ])
    monkeypatch.setattr(session_registry.uuid, 'uuid4', lambda: next(generated))

    first = isolated_registry.create_session()
    second = isolated_registry.create_session()

    assert first.session_id == 'aaaaaaaa'
    assert second.session_id == 'bbbbbbbb'
    assert len(isolated_registry.get_all()) == 2


def test_concurrent_creations_are_unique(isolated_registry) -> None:
    """Des créations parallèles produisent toutes une session distincte."""
    with ThreadPoolExecutor(max_workers=12) as executor:
        sessions = list(executor.map(lambda _index: isolated_registry.create_session(), range(100)))

    session_ids = {session.session_id for session in sessions}
    assert len(session_ids) == 100
    assert len(isolated_registry.get_all()) == 100


def test_get_returns_snapshot_not_mutable_registry_object(isolated_registry) -> None:
    """Modifier un objet lu ne contourne pas le verrou ni la méthode update."""
    created = isolated_registry.create_session()
    snapshot = isolated_registry.get(created.session_id)

    snapshot.status = 'completed'

    assert isolated_registry.get(created.session_id).status == 'pending'


def test_update_validates_fields_and_status(isolated_registry) -> None:
    """Seuls les champs connus et les statuts contractuels sont acceptés."""
    session = isolated_registry.create_session()

    assert isolated_registry.update(session.session_id, status='running', exit_code=0) is True
    assert isolated_registry.get(session.session_id).status == 'running'
    with pytest.raises(ValueError, match='Champs de session inconnus'):
        isolated_registry.update(session.session_id, injected='value')
    with pytest.raises(ValueError, match='Statut de session invalide'):
        isolated_registry.update(session.session_id, status='unknown')
    assert isolated_registry.update('absente', status='running') is False


def test_running_snapshots_count_and_remove(isolated_registry) -> None:
    """Le filtrage, le comptage et la suppression partagent le même état verrouillé."""
    first = isolated_registry.create_session()
    second = isolated_registry.create_session()
    isolated_registry.update(first.session_id, status='running')

    assert list(isolated_registry.get_running()) == [first.session_id]
    assert isolated_registry.count_running() == 1
    assert isolated_registry.remove(first.session_id) is True
    assert isolated_registry.remove(first.session_id) is False
    assert isolated_registry.get(second.session_id) is not None


@pytest.mark.parametrize('session_id', ['', '../escape', 'a/b', r'a\\b', 'avec espace'])
def test_stop_signal_rejects_unsafe_session_ids(
    isolated_registry,
    session_id: str,
) -> None:
    """Un identifiant ne peut pas construire un chemin hors du dossier temp."""
    with pytest.raises(ValueError, match='Identifiant de session invalide'):
        isolated_registry.stop_signal_path(session_id)


def test_stop_signal_accepts_generated_and_legacy_safe_ids(isolated_registry) -> None:
    """Les identifiants générés et les formes tiretées existantes restent valides."""
    path = isolated_registry.stop_signal_path('session-1_safe')

    assert path.name == 'stop_signal_session-1_safe.txt'