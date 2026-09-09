"""Tests unitaires de la carte d'identité d'un run."""

import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from services.execution import run_meta

# Capturée à l'import, avant que le garde-fou global de conftest ne la remplace.
_REAL_CURRENT_COMMIT = run_meta.current_commit


@pytest.fixture
def reports(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirige le dossier de rapports vers un emplacement temporaire."""
    reports_dir = tmp_path / "report"
    monkeypatch.setattr(run_meta.paths, "REPORTS", reports_dir)
    return reports_dir


def test_write_records_commit_environment_and_caller_fields(
    monkeypatch: pytest.MonkeyPatch,
    reports: Path,
) -> None:
    """Le contexte réunit ce que le service sait et ce que seul l'appelant connaît."""
    monkeypatch.setattr(run_meta, "current_commit", Mock(return_value="a1b2c3d"))
    monkeypatch.setattr(
        run_meta.environments, "active_environment", Mock(return_value="saucedemo")
    )

    run_meta.write("2026_09_06-101530", browser="firefox", device="tablet")

    written = json.loads((reports / "2026_09_06-101530" / run_meta.META_FILE).read_text("utf-8"))
    assert written == {
        "commit": "a1b2c3d",
        "environment": "saucedemo",
        "browser": "firefox",
        "device": "tablet",
    }


def test_read_returns_empty_context_for_runs_without_trace(reports: Path) -> None:
    """Un run antérieur à cette trace n'en a pas : ce n'est pas une erreur."""
    run_dir = reports / "ancien_run"
    run_dir.mkdir(parents=True)

    assert run_meta.read(run_dir) == {}


def test_read_ignores_a_damaged_trace(reports: Path) -> None:
    """Un fichier illisible ne doit pas empêcher d'exploiter le reste du run."""
    run_dir = reports / "run_abime"
    run_dir.mkdir(parents=True)
    (run_dir / run_meta.META_FILE).write_text("{ json invalide", encoding="utf-8")

    assert run_meta.read(run_dir) == {}


def test_write_failure_never_blocks_the_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Une écriture impossible se journalise, elle n'interrompt pas le lancement."""
    occupied = tmp_path / "report"
    occupied.write_text("ce chemin n'est pas un dossier", encoding="utf-8")
    monkeypatch.setattr(run_meta.paths, "REPORTS", occupied)
    monkeypatch.setattr(run_meta, "current_commit", Mock(return_value=None))

    run_meta.write("2026_09_06-101530")


def test_current_commit_is_none_outside_a_git_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hors dépôt Git, l'absence de commit se dit au lieu de casser l'ingestion."""
    monkeypatch.setattr(
        run_meta.subprocess,
        "run",
        Mock(side_effect=subprocess.CalledProcessError(128, "git")),
    )

    assert _REAL_CURRENT_COMMIT() is None
