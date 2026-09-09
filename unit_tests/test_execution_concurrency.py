"""Tests d'isolation des dossiers et sélections entre sessions concurrentes."""

import datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from services.execution import commands, orchestrator


class FixedDateTime(datetime.datetime):
    """Horloge déterministe permettant de simuler plusieurs runs la même seconde."""

    @classmethod
    def now(cls, tz=None):
        """Retourne toujours le même instant, avec ou sans fuseau."""
        value = cls(2026, 7, 27, 15, 30, 0)
        return value.replace(tzinfo=tz) if tz else value


def test_same_second_workflows_get_distinct_session_report_folders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deux sessions identiques lancées ensemble produisent deux noms de run."""
    stamps: list[str] = []
    monkeypatch.setattr(orchestrator.datetime, "datetime", FixedDateTime)
    monkeypatch.setattr(
        orchestrator,
        "get_smoke_cmd",
        lambda stamp, **_kwargs: stamps.append(stamp) or ["robot"],
    )
    monkeypatch.setattr(orchestrator, "execute_rf_commands", Mock(return_value=0))

    orchestrator.run_workflow(
        "smoke",
        session_id="session-a",
        browser="chromium",
        device="desktop",
    )
    orchestrator.run_workflow(
        "smoke",
        session_id="session-b",
        browser="chromium",
        device="desktop",
    )

    assert stamps == [
        "2026_07_27-153000_chromium_desktop_session-a",
        "2026_07_27-153000_chromium_desktop_session-b",
    ]


def test_workflow_without_session_keeps_historical_stamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un appel direct hors API conserve le timestamp historique sans suffixe."""
    stamps: list[str] = []
    monkeypatch.setattr(orchestrator.datetime, "datetime", FixedDateTime)
    monkeypatch.setattr(
        orchestrator,
        "get_smoke_cmd",
        lambda stamp, **_kwargs: stamps.append(stamp) or ["robot"],
    )
    monkeypatch.setattr(orchestrator, "execute_rf_commands", Mock(return_value=0))

    orchestrator.run_workflow("smoke")

    assert stamps == ["2026_07_27-153000"]


def test_randomized_selections_are_stored_in_distinct_report_folders(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Chaque commande aléatoire conserve uniquement sa propre sélection."""
    monkeypatch.setattr(commands.paths, "REPORTS", tmp_path)

    first_command = commands.get_randomized_cmd(
        "run_session-a",
        ["Test A", "Test B"],
    )
    second_command = commands.get_randomized_cmd(
        "run_session-b",
        ["Test C"],
    )

    first_args = Path(first_command[first_command.index("--argumentfile") + 1])
    second_args = Path(second_command[second_command.index("--argumentfile") + 1])
    assert first_args == tmp_path / "run_session-a" / "selected_tests.args"
    assert second_args == tmp_path / "run_session-b" / "selected_tests.args"
    assert first_args != second_args
    assert first_args.read_text(encoding="utf-8") == "--test Test A\n--test Test B\n"
    assert second_args.read_text(encoding="utf-8") == "--test Test C\n"


def test_rerun_keeps_selection_at_run_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Le fichier d'audit reste à la racine même si Robot écrit dans Output_original."""
    monkeypatch.setattr(commands.paths, "REPORTS", tmp_path)

    command = commands.get_randomized_cmd(
        "run_session-rerun",
        ["Test A"],
        rerun_failed=True,
    )

    args_file = Path(command[command.index("--argumentfile") + 1])
    output_dir = Path(command[command.index("-d") + 1])
    assert args_file == tmp_path / "run_session-rerun" / "selected_tests.args"
    assert output_dir == tmp_path / "run_session-rerun" / "Output_original"
