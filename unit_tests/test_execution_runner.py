"""Tests unitaires du runner de commandes Robot Framework."""

from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest
import requests

from services.execution import runner


def test_run_rf_command_passes_argument_list_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """La liste d'arguments est transmise directement à subprocess sans shell."""
    command = ["robot", "-i", "smoke & valeur"]
    popen = Mock(return_value=SimpleNamespace(wait=lambda timeout=None: 3))
    monkeypatch.setattr(runner.subprocess, "Popen", popen)

    result = runner.run_rf_command(command, session_id="session-1")

    assert result == 3
    assert popen.call_args.args[0] == command


def test_run_rf_command_rejects_shell_string(monkeypatch: pytest.MonkeyPatch) -> None:
    """Une commande construite en chaîne est refusée avant tout lancement."""
    popen = Mock()
    monkeypatch.setattr(runner.subprocess, "Popen", popen)

    with pytest.raises(TypeError, match="listes d'arguments"):
        runner.run_rf_command("robot -i smoke")

    popen.assert_not_called()


def test_run_rf_command_returns_launch_failure_when_executable_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un exécutable absent retourne le code réservé aux erreurs de lancement."""
    monkeypatch.setattr(runner.subprocess, "Popen", Mock(side_effect=FileNotFoundError))

    result = runner.run_rf_command(["robot"], session_id="session-1")

    assert result == runner.EXIT_LAUNCH_FAILED


def test_execute_rf_commands_stops_after_first_nonzero_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """La séquence s'arrête dès qu'une commande Robot retourne un échec."""
    commands = [["robot", "test-a"], ["robot", "test-b"], ["robot", "test-c"]]
    run_command = Mock(side_effect=[0, 2, 0])
    notify = Mock()
    monkeypatch.setattr(runner, "_get_stop_signal_path", lambda _session: tmp_path / "stop")
    monkeypatch.setattr(runner, "run_rf_command", run_command)
    monkeypatch.setattr(runner, "_was_manually_stopped", Mock(return_value=False))
    monkeypatch.setattr(runner, "_notify_execution_complete", notify)

    result = runner.execute_rf_commands(commands)

    assert result == 2
    assert run_command.call_count == 2
    notify.assert_called_once_with(None)


def test_manual_stop_updates_session_and_notifies(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Un arrêt manuel marque la session comme stoppée et publie sa fin."""
    update = Mock()
    notify = Mock()
    monkeypatch.setattr(runner, "_get_stop_signal_path", lambda _session: tmp_path / "stop")
    monkeypatch.setattr(runner, "run_rf_command", Mock(return_value=0))
    monkeypatch.setattr(runner, "_was_manually_stopped", Mock(return_value=True))
    monkeypatch.setattr(runner.registry, "update", update)
    monkeypatch.setattr(runner, "_notify_execution_complete", notify)

    result = runner.execute_rf_commands([["robot", "test"]], session_id="session-1")

    assert result == 0
    assert update.call_args_list == [
        call("session-1", status="running"),
        call("session-1", status="stopped", exit_code=0),
    ]
    notify.assert_called_once_with("session-1")


def test_format_rf_command_for_log_masks_sensitive_variables() -> None:
    """Les secrets sont masqués dans le journal sans modifier la commande source."""
    command = [
        "robot",
        "-v",
        "RF_PASSWORD:secret-1",
        "--variable",
        "ACCESS_TOKEN:secret-2",
        "--variable=API_KEY:secret-3",
        "-v",
        "BROWSER:chromium",
    ]

    formatted = runner.format_rf_command_for_log(command)

    assert "secret-1" not in formatted
    assert "secret-2" not in formatted
    assert "secret-3" not in formatted
    assert "RF_PASSWORD:***" in formatted
    assert "ACCESS_TOKEN:***" in formatted
    assert "API_KEY:***" in formatted
    assert "BROWSER:chromium" in formatted
    assert command[2] == "RF_PASSWORD:secret-1"


def test_notification_failure_does_not_fail_the_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Une API indisponible reste une erreur de notification, pas une erreur de run."""
    post = Mock(side_effect=requests.ConnectionError("API indisponible"))
    monkeypatch.setattr(runner.requests, "post", post)

    runner._notify_execution_complete("session-1")

    post.assert_called_once_with(
        f"{runner.API_BASE_URL}/execution-complete",
        json={"session_id": "session-1"},
        timeout=5,
    )