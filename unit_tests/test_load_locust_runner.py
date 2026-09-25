"""Tests unitaires du runner Locust sans lancer de processus de charge.

La plomberie partagée avec k6 (POST, historique, résultat, arrêt) est couverte par
`test_load_runner_common.py` : ici, seul ce qui est propre à Locust.
"""

import pytest

from services.load import locust_runner


def test_single_process_run_passes_no_forking_option() -> None:
    """Sans répartition demandée, la commande reste inchangée."""
    assert locust_runner._processes_args({}, "sid") == []
    assert locust_runner._processes_args({"processes": 1}, "sid") == []


def test_multi_process_run_forks_on_posix(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sur un système compatible, la charge est répartie sur plusieurs cœurs."""
    monkeypatch.setattr(locust_runner.sys, "platform", "linux")

    assert locust_runner._processes_args({"processes": 8}, "sid") == ["--processes", "8"]


def test_multi_process_run_is_refused_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """Locust ne sait pas forker sous Windows : on le dit au lieu de l'ignorer."""
    monkeypatch.setattr(locust_runner.sys, "platform", "win32")
    logs = []
    monkeypatch.setattr(locust_runner.common, "emit_log", lambda sid, msg: logs.append(msg))

    assert locust_runner._processes_args({"processes": 8}, "sid") == []
    assert "Windows" in logs[0]