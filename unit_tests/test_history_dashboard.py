"""Tests unitaires du dashboard de tendances (sans lancer robotdashboard)."""

from pathlib import Path

import pytest

from services.history import dashboard


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[list[str]]:
    """Capture les arguments passés à robotdashboard, sans jamais démarrer de processus."""
    recorded: list[list[str]] = []

    def fake_run(args: list[str], _step: str) -> bool:
        recorded.append(args)
        return True

    monkeypatch.setattr(dashboard, "_run", fake_run)
    monkeypatch.setattr(dashboard, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(dashboard, "DASHBOARD_FILE", tmp_path / "dashboard.html")
    monkeypatch.setattr(dashboard, "output_of", lambda run_dir: run_dir / "output.xml")
    (tmp_path / "dashboard.html").write_text("<html/>", encoding="utf-8")
    return recorded


def _added_runs(calls: list[list[str]]) -> list[str]:
    """Retourne les runs versés, lus dans les liens vers leur log."""
    return [
        args[args.index("--logurl") + 1].rsplit("/", 1)[-1]
        for args in calls
        if "--logurl" in args
    ]


def test_adds_only_runs_the_history_kept(monkeypatch: pytest.MonkeyPatch, calls) -> None:
    """L'ingestion écarte les runs d'un dépôt voisin ; le dashboard hérite de ce tri."""
    monkeypatch.setattr(dashboard.store, "stored_run_ids", lambda: ["run_a", "run_b"])

    assert dashboard.refresh() is not None
    assert _added_runs(calls) == ["run_a", "run_b"]


def test_does_not_add_a_run_twice(monkeypatch: pytest.MonkeyPatch, calls) -> None:
    """Reverser chaque run connu à chaque consultation coûterait un processus par run."""
    monkeypatch.setattr(dashboard.store, "stored_run_ids", lambda: ["run_a"])
    dashboard.refresh()
    calls.clear()

    dashboard.refresh()

    assert _added_runs(calls) == []


def test_purges_the_database_on_the_retention_delay(monkeypatch: pytest.MonkeyPatch,
                                                    calls) -> None:
    """Garder en base des runs dont le rapport est purgé laisserait des liens morts."""
    monkeypatch.setattr(dashboard.store, "stored_run_ids", list)

    dashboard.refresh()

    purge = next(args for args in calls if "-r" in args)
    assert purge[purge.index("-r") + 1] == f"age={dashboard.MAX_AGE_DAYS}d"


def test_purge_does_not_write_a_dashboard_of_its_own(monkeypatch: pytest.MonkeyPatch,
                                                     calls) -> None:
    """La génération est active par défaut : la purge déposait un HTML à la racine du dépôt."""
    monkeypatch.setattr(dashboard.store, "stored_run_ids", list)

    dashboard.refresh()

    purge = next(args for args in calls if "-r" in args)
    assert purge[purge.index("-g") + 1] == "false"


def test_reports_failure_when_the_html_is_missing(monkeypatch: pytest.MonkeyPatch,
                                                  calls) -> None:
    """Servir un dashboard absent afficherait une page blanche sans expliquer pourquoi."""
    monkeypatch.setattr(dashboard.store, "stored_run_ids", list)
    dashboard.DASHBOARD_FILE.unlink()

    assert dashboard.refresh() is None
