"""Arrêt manuel : ce qu'un clic sur « Arrêter » doit réellement arrêter."""

import subprocess
from types import SimpleNamespace

import pytest

from services.execution import orchestrator, runner


class _FakeProcess:
    """Process qui ne se termine qu'une fois interrompu."""

    def __init__(self, stops_after: int = 1) -> None:
        self.stops_after = stops_after
        self.interrupted = False
        self.killed = False
        self.signals = []
        self._polls = 0

    def wait(self, timeout=None):
        if self.interrupted or self.killed:
            return 143
        self._polls += 1
        raise subprocess.TimeoutExpired('robot', timeout or 0)

    def send_signal(self, sig):
        self.signals.append(sig)
        self.interrupted = True

    def terminate(self):
        self.interrupted = True

    def kill(self):
        self.killed = True


def test_a_running_robot_is_interrupted_when_a_stop_is_asked(monkeypatch) -> None:
    """Sans cela, le signal n'est lu qu'entre deux commandes : rien ne s'arrête."""
    monkeypatch.setattr(runner, '_was_manually_stopped', lambda _sid: True)
    process = _FakeProcess()

    assert runner._wait_or_stop(process, 'session-1') == 143
    assert process.interrupted is True
    assert process.killed is False


def test_a_robot_that_ignores_the_interruption_is_killed(monkeypatch) -> None:
    """Un run qui ne rend pas la main bloquerait la session pour toujours."""
    monkeypatch.setattr(runner, '_was_manually_stopped', lambda _sid: True)
    monkeypatch.setattr(runner, 'GRACEFUL_STOP_SECONDS', runner.STOP_POLL_SECONDS)

    class _Deaf(_FakeProcess):
        def send_signal(self, sig):
            self.signals.append(sig)

        def terminate(self):
            pass

    process = _Deaf()

    runner._wait_or_stop(process, 'session-1')

    assert process.killed is True


def test_an_untouched_run_is_never_interrupted(monkeypatch) -> None:
    """Le run nominal ne doit rien subir de la surveillance d'arrêt."""
    monkeypatch.setattr(runner, '_was_manually_stopped', lambda _sid: False)
    process = SimpleNamespace(wait=lambda timeout=None: 0)

    assert runner._wait_or_stop(process, 'session-1') == 0


def test_a_stopped_run_does_not_replay_its_failures(monkeypatch) -> None:
    """Les tests non joués d'un run interrompu ne sont pas des échecs à rejouer."""
    replayed = []
    monkeypatch.setattr(orchestrator, 'execute_rf_commands', lambda *a, **k: 1)
    monkeypatch.setattr(orchestrator, 'was_manually_stopped', lambda _sid: True)
    monkeypatch.setattr(orchestrator, '_notify_execution_complete', lambda _sid: None)
    monkeypatch.setattr(
        orchestrator, 'rerun_failed_tests', lambda *a, **k: replayed.append(a)
    )

    orchestrator.run_workflow('smoke', rerun_failed=True, session_id='session-1')

    assert replayed == []


def test_a_failed_run_still_replays_its_failures(monkeypatch) -> None:
    """Le rejeu reste la règle quand personne n'a demandé l'arrêt."""
    replayed = []
    monkeypatch.setattr(orchestrator, 'execute_rf_commands', lambda *a, **k: 1)
    monkeypatch.setattr(orchestrator, 'was_manually_stopped', lambda _sid: False)
    monkeypatch.setattr(orchestrator, '_notify_execution_complete', lambda _sid: None)
    monkeypatch.setattr(
        orchestrator, 'rerun_failed_tests', lambda *a, **k: replayed.append(a)
    )

    orchestrator.run_workflow('smoke', rerun_failed=True, session_id='session-1')

    assert len(replayed) == 1


@pytest.mark.parametrize(
    'phase, expected',
    [('run', ':session-1:run'), ('rerun', ':session-1:rerun')],
)
def test_the_listener_knows_which_phase_it_reports(phase, expected) -> None:
    """Le rejeu envoie son propre avancement : l'interface doit pouvoir les distinguer."""
    from services.execution import commands

    argument = commands._listener_arg('session-1', phase=phase)[1]

    assert argument.endswith(expected)
