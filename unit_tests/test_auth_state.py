"""État d'authentification : le fichier de session ne doit jamais rester exposé."""

import os
import tempfile
import time
from pathlib import Path

import pytest

from libraries.resources.common import auth_state


@pytest.fixture(autouse=True)
def isolated_temp(tmp_path, monkeypatch):
    """Chaque test a son propre dossier temporaire, et repart sans état enregistré.

    `mkdtemp` appelle `gettempdir()` : le patch suffit à confiner la sonde.
    """
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    auth_state._private_dir = None
    yield
    auth_state._private_dir = None


def _saved_by_browser(report_dir: Path) -> Path:
    """Reproduit ce que fait `Save Storage State` : écrire dans le dossier de rapport."""
    state_dir = report_dir / "browser" / "state"
    state_dir.mkdir(parents=True)
    saved = state_dir / "4438704f.json"
    saved.write_text('{"cookies": [{"name": "orangehrm"}]}', encoding="utf-8")
    return saved


def test_the_state_leaves_the_report_folder(tmp_path) -> None:
    """Le rapport est archivé par la CI et servi par /logs/ : le cookie n'y a rien à faire."""
    report_dir = tmp_path / "report"
    saved = _saved_by_browser(report_dir)

    stashed = Path(auth_state.stash_auth_state(str(saved)))

    assert not saved.exists()
    assert report_dir not in stashed.parents
    assert stashed.read_text(encoding="utf-8").startswith('{"cookies"')


def test_two_runs_do_not_share_a_file(tmp_path) -> None:
    """Un run en matrice lance N processus : un chemin commun serait une collision."""
    first = Path(auth_state.stash_auth_state(str(_saved_by_browser(tmp_path / "a"))))
    auth_state._private_dir = None  # le second processus repart de zéro

    second = Path(auth_state.stash_auth_state(str(_saved_by_browser(tmp_path / "b"))))

    assert first.parent != second.parent


def test_discarding_removes_the_session_from_disk(tmp_path) -> None:
    """Une session vivante ne doit pas survivre au run qui l'a ouverte."""
    stashed = Path(auth_state.stash_auth_state(str(_saved_by_browser(tmp_path / "report"))))

    auth_state.discard_auth_state()

    assert not stashed.parent.exists()


def test_discarding_without_a_session_is_harmless() -> None:
    """Le teardown s'exécute aussi quand le setup a échoué avant d'enregistrer."""
    auth_state.discard_auth_state()


def test_a_folder_left_by_a_killed_run_is_cleaned_up(tmp_path) -> None:
    """Le bouton « Arrêter » peut tuer le processus avant son teardown."""
    orphan = tmp_path / f"{auth_state._PREFIX}killed"
    orphan.mkdir()
    (orphan / "storage_state.json").write_text("{}", encoding="utf-8")
    stale = time.time() - auth_state._STALE_AFTER_S - 60
    os.utime(orphan, (stale, stale))

    auth_state.stash_auth_state(str(_saved_by_browser(tmp_path / "report")))

    assert not orphan.exists()


def test_a_folder_from_a_concurrent_run_is_left_alone(tmp_path) -> None:
    """Purger trop large reviendrait à déconnecter le run d'à côté."""
    neighbour = tmp_path / f"{auth_state._PREFIX}running"
    neighbour.mkdir()

    auth_state.stash_auth_state(str(_saved_by_browser(tmp_path / "report")))

    assert neighbour.exists()
