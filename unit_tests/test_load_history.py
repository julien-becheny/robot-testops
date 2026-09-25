"""Tests unitaires de l'historique JSONL des tests de charge."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from services.load import history


@pytest.fixture
def history_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirige l'historique vers un fichier temporaire propre à chaque test."""
    file_path = tmp_path / "load_history.jsonl"
    monkeypatch.setattr(history, "HISTORY_FILE", file_path)
    return file_path


def test_save_run_generates_system_id_and_timestamp(
    monkeypatch: pytest.MonkeyPatch,
    history_file: Path,
) -> None:
    """Le service impose son identifiant et son horodatage dans le JSONL."""
    fake_uuid = SimpleNamespace(hex="abcdef1234567890")  # pragma: allowlist secret
    monkeypatch.setattr(history.uuid, "uuid4", Mock(return_value=fake_uuid))
    monkeypatch.setattr(history.time, "time", Mock(return_value=1234.5))

    record = history.save_run({"id": "fourni", "ts": 0, "status": "ok"})

    assert record["id"] == fake_uuid.hex[:12]
    assert record["ts"] == 1234.5
    assert record["status"] == "ok"
    assert json.loads(history_file.read_text(encoding="utf-8")) == record


def test_list_runs_returns_newest_entries_with_limit(history_file: Path) -> None:
    """La lecture renverse l'ordre d'écriture et respecte la limite demandée."""
    entries = [{"id": "ancien"}, {"id": "milieu"}, {"id": "récent"}]
    history_file.write_text(
        "\n".join(json.dumps(entry, ensure_ascii=False) for entry in entries) + "\n",
        encoding="utf-8",
    )

    assert history.list_runs(limit=2) == [{"id": "récent"}, {"id": "milieu"}]
    assert history.list_runs(limit=0) == []


def test_list_runs_ignores_invalid_and_non_object_lines(history_file: Path) -> None:
    """Les lignes corrompues ou ne représentant pas un run sont ignorées."""
    history_file.write_text(
        '{"id": "valide"}\n{json invalide\n[1, 2, 3]\n',
        encoding="utf-8",
    )

    assert history.list_runs() == [{"id": "valide"}]


def test_trim_keeps_only_latest_configured_runs(
    monkeypatch: pytest.MonkeyPatch,
    history_file: Path,
) -> None:
    """La limitation conserve uniquement les dernières lignes non vides."""
    monkeypatch.setattr(history, "_MAX_RUNS", 3)
    history_file.write_text("1\n2\n3\n4\n5\n", encoding="utf-8")

    history._trim()

    assert history_file.read_text(encoding="utf-8").splitlines() == ["3", "4", "5"]


def test_clear_history_removes_file(history_file: Path) -> None:
    """La suppression efface le fichier JSONL lorsqu'il existe."""
    history_file.write_text('{"id": "run"}\n', encoding="utf-8")

    history.clear_history()

    assert not history_file.exists()


def test_write_error_does_not_fail_load_run(history_file: Path) -> None:
    """Une erreur disque conserve le résultat en mémoire sans lever d'exception."""
    history_file.mkdir()

    record = history.save_run({"status": "ok"})

    assert record["status"] == "ok"
    assert "id" in record
    assert "ts" in record


def test_read_error_returns_empty_history(history_file: Path) -> None:
    """Un chemin illisible retourne une liste vide au lieu de casser l'API."""
    history_file.mkdir()

    assert history.list_runs() == []