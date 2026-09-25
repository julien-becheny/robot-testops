"""Tests unitaires de la persistance de la mémoire des exécutions."""

import json
from pathlib import Path

import pytest

from services.history import store


@pytest.fixture
def history_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirige l'historique vers un fichier temporaire propre à chaque test."""
    file_path = tmp_path / "test_history.jsonl"
    monkeypatch.setattr(store, "HISTORY_FILE", file_path)
    monkeypatch.setattr(store, "STATE_FILE", tmp_path / "test_history_state.json")
    return file_path


def _entry(run_id: str, test: str, status: str = "PASS") -> dict:
    return {"run_id": run_id, "test": test, "status": status}


def test_append_writes_one_line_per_test_with_schema_version(history_file: Path) -> None:
    """Chaque entrée porte la version du format pour se reconnaître plus tard."""
    store.append([_entry("run_1", "Suite.A"), _entry("run_1", "Suite.B", "FAIL")])

    lines = [json.loads(line) for line in history_file.read_text("utf-8").splitlines()]
    assert [line["test"] for line in lines] == ["Suite.A", "Suite.B"]
    assert {line["schema"] for line in lines} == {store.SCHEMA}


def test_append_ignores_an_empty_run(history_file: Path) -> None:
    """Un run sans test ne crée pas de fichier : il n'y a rien à retenir."""
    store.append([])

    assert not history_file.exists()


def test_read_entries_keeps_the_latest_runs_in_chronological_order(
    history_file: Path,
) -> None:
    """L'analyse lit les résultats dans l'ordre où ils sont tombés."""
    store.append([_entry("run_1", "Suite.A")])
    store.append([_entry("run_2", "Suite.A")])
    store.append([_entry("run_3", "Suite.A", "FAIL")])

    kept = store.read_entries(runs=2)

    assert [entry["run_id"] for entry in kept] == ["run_2", "run_3"]
    assert store.read_entries(runs=0) == []


def test_read_entries_ignores_damaged_lines(history_file: Path) -> None:
    """Une ligne corrompue est sautée, elle ne rend pas tout l'historique inutilisable."""
    history_file.write_text(
        '{"run_id": "run_1", "test": "Suite.A"}\n{json invalide\n[1, 2, 3]\n',
        encoding="utf-8",
    )

    assert [entry["test"] for entry in store.read_entries(runs=5)] == ["Suite.A"]


def test_stored_run_ids_are_deduplicated_and_ordered(history_file: Path) -> None:
    """Les identifiants servent à savoir ce qui a déjà été ingéré."""
    store.append([_entry("run_1", "Suite.A"), _entry("run_1", "Suite.B")])
    store.append([_entry("run_2", "Suite.A")])

    assert store.stored_run_ids() == ["run_1", "run_2"]


def test_rotation_drops_the_oldest_runs_with_all_their_entries(
    monkeypatch: pytest.MonkeyPatch,
    history_file: Path,
) -> None:
    """La rotation raisonne en runs, pas en lignes : un run part avec tous ses tests."""
    monkeypatch.setattr(store, "MAX_RUNS_KEPT", 2)
    store.append([_entry("run_1", "Suite.A"), _entry("run_1", "Suite.B")])
    store.append([_entry("run_2", "Suite.A")])
    store.append([_entry("run_3", "Suite.A")])

    assert store.stored_run_ids() == ["run_2", "run_3"]


def test_write_failure_never_raises(history_file: Path) -> None:
    """L'historique ne doit jamais faire échouer ce qui l'alimente."""
    history_file.mkdir()

    store.append([_entry("run_1", "Suite.A")])

    assert store.read_entries(runs=5) == []


def test_clear_removes_the_history(history_file: Path) -> None:
    """La remise à zéro efface le fichier lorsqu'il existe."""
    store.append([_entry("run_1", "Suite.A")])
    store.set_scan_watermark(1234.5)

    store.clear()

    assert not history_file.exists()
    assert store.scan_watermark() == 0.0


def test_scan_watermark_defaults_to_zero_on_first_pass(history_file: Path) -> None:
    """Sans repère, tout le dossier de rapports est à balayer."""
    assert store.scan_watermark() == 0.0


def test_scan_watermark_survives_a_damaged_state_file(history_file: Path) -> None:
    """Un repère illisible fait recommencer le balayage, il ne bloque pas la lecture."""
    store.STATE_FILE.write_text("{ pas du json", encoding="utf-8")

    assert store.scan_watermark() == 0.0


def test_scan_watermark_is_kept_between_passes(history_file: Path) -> None:
    """Le repère évite de relire les résultats déjà examinés."""
    store.set_scan_watermark(1234.5)

    assert store.scan_watermark() == 1234.5
