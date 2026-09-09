"""Tests unitaires de l'orchestration des workflows Robot Framework."""

import json
from unittest.mock import Mock

from services.execution import orchestrator


def test_smoke_workflow_builds_and_executes_one_command(monkeypatch) -> None:
    """Le workflow smoke construit puis transmet une seule commande au runner."""
    command = ["robot", "--dryrun"]
    build_smoke = Mock(return_value=command)
    execute = Mock(return_value=0)
    monkeypatch.setattr(orchestrator, "get_smoke_cmd", build_smoke)
    monkeypatch.setattr(orchestrator, "execute_rf_commands", execute)

    orchestrator.run_workflow("smoke", browser="firefox", device="mobile")

    build_smoke.assert_called_once()
    _, build_kwargs = build_smoke.call_args
    assert build_kwargs == {
        "session_id": None,
        "browser": "firefox",
        "device": "mobile",
    }
    execute.assert_called_once_with([command], session_id=None, notify_complete=True)


def test_unknown_workflow_does_not_execute_a_command(monkeypatch) -> None:
    """Un identifiant de workflow inconnu est refusé avant tout lancement."""
    execute = Mock()
    monkeypatch.setattr(orchestrator, "execute_rf_commands", execute)

    orchestrator.run_workflow("inconnu")

    execute.assert_not_called()


def test_randomized_workflow_respects_requested_selection_count(monkeypatch) -> None:
    """Le workflow aléatoire transmet exactement le nombre de tests demandé."""
    matching_tests = [{"name": "Test A"}, {"name": "Test B"}, {"name": "Test C"}]
    selected_tests = ["Test A", "Test C"]
    build_randomized = Mock(return_value=["robot", "--randomize", "all"])
    execute = Mock(return_value=0)
    sample = Mock(return_value=selected_tests)
    monkeypatch.setattr(orchestrator, "get_matching_tests", Mock(return_value=matching_tests))
    monkeypatch.setattr(orchestrator.random, "sample", sample)
    monkeypatch.setattr(orchestrator, "get_randomized_cmd", build_randomized)
    monkeypatch.setattr(orchestrator, "execute_rf_commands", execute)

    orchestrator.run_workflow(
        "randomized",
        include_tags=["regression"],
        exclude_tags=["lent"],
        is_random=True,
        nb_selection=2,
        device="tablet",
    )

    sample.assert_called_once_with(["Test A", "Test B", "Test C"], 2)
    build_args, build_kwargs = build_randomized.call_args
    assert build_args[1:] == (selected_tests, False)
    assert build_kwargs["device"] == "tablet"
    execute.assert_called_once_with(
        [["robot", "--randomize", "all"]],
        session_id=None,
        notify_complete=True,
    )


def test_failed_workflow_with_rerun_replays_failures_and_notifies(
    monkeypatch, tmp_path
) -> None:
    """Un run en échec avec rerun rejoue les échecs puis notifie sa fin."""
    command = ["robot", "--dryrun"]
    execute = Mock(return_value=2)
    rerun = Mock()
    notify = Mock()
    monkeypatch.setattr(orchestrator, "get_smoke_cmd", Mock(return_value=command))
    monkeypatch.setattr(orchestrator, "execute_rf_commands", execute)
    monkeypatch.setattr(orchestrator, "rerun_failed_tests", rerun)
    monkeypatch.setattr(orchestrator, "_notify_execution_complete", notify)
    monkeypatch.setattr(
        orchestrator.paths, "get_report_folder", lambda stamp: tmp_path / stamp
    )

    orchestrator.run_workflow("smoke", rerun_failed=True)

    execute.assert_called_once_with([command], session_id=None, notify_complete=False)
    rerun.assert_called_once()
    notify.assert_called_once_with(None)


def test_run_records_the_context_of_the_run(monkeypatch, disposable_run_context) -> None:
    """Sans cette trace, l'analyse ne peut pas distinguer un test fragile d'une régression."""
    monkeypatch.setattr(orchestrator, "get_smoke_cmd", Mock(return_value=["robot"]))
    monkeypatch.setattr(orchestrator, "execute_rf_commands", Mock(return_value=0))

    orchestrator.run_workflow("smoke", browser="firefox", device="mobile")

    written = list(disposable_run_context.glob("*/run_meta.json"))
    assert len(written) == 1
    context = json.loads(written[0].read_text(encoding="utf-8"))
    assert context["commit"] == "a1b2c3d"
    assert context["workflow"] == "smoke"
    assert context["browser"] == "firefox"
    assert context["device"] == "mobile"