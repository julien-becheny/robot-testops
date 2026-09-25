"""Tests du contrat HTTP de la santé de la suite."""

from unittest.mock import Mock

import pytest

from api.app import app


@pytest.fixture
def client():
    """Retourne le client Flask sans démarrer de serveur réseau."""
    return app.test_client()


def test_suite_health_ingests_before_answering(
    monkeypatch: pytest.MonkeyPatch,
    client,
) -> None:
    """Sans ingestion préalable, la page afficherait l'état d'avant le dernier run."""
    from api.routes import history_routes

    ingest = Mock(return_value=1)
    report = {"window": 30, "runs": 6, "counts": {}, "quarantined": 0, "tests": []}
    monkeypatch.setattr(history_routes, "ingest_new_runs", ingest)
    monkeypatch.setattr(history_routes, "suite_health", Mock(return_value=report))

    response = client.get('/suite-health')

    assert response.status_code == 200
    assert response.get_json() == report
    ingest.assert_called_once_with()


def test_run_diff_ingests_before_answering(
    monkeypatch: pytest.MonkeyPatch,
    client,
) -> None:
    """Le dernier run peut venir de la ligne de commande : sans ingestion, il manque."""
    from api.routes import history_routes

    ingest = Mock(return_value=1)
    report = {"run": None, "baseline": None, "same_commit": False, "counts": {}, "changes": []}
    monkeypatch.setattr(history_routes, "ingest_new_runs", ingest)
    monkeypatch.setattr(history_routes, "last_run_diff", Mock(return_value=report))

    response = client.get('/run-diff')

    assert response.status_code == 200
    assert response.get_json() == report
    ingest.assert_called_once_with()


def test_suite_health_purges_after_ingesting(
    monkeypatch: pytest.MonkeyPatch,
    client,
) -> None:
    """Purger avant de lire effacerait des runs jamais historisés : l'ordre est le garde-fou."""
    from api.routes import history_routes

    order = []
    monkeypatch.setattr(history_routes, "ingest_new_runs",
                        lambda: order.append('ingest'))
    monkeypatch.setattr(history_routes.retention, "purge_old_runs",
                        lambda: order.append('purge'))
    monkeypatch.setattr(history_routes, "suite_health", Mock(return_value={}))

    client.get('/suite-health')

    assert order == ['ingest', 'purge']


def test_health_dashboard_says_when_it_could_not_be_built(
    monkeypatch: pytest.MonkeyPatch,
    client,
) -> None:
    """Sans cela, l'onglet ouvert afficherait une page blanche sans expliquer pourquoi."""
    from api.routes import history_routes

    monkeypatch.setattr(history_routes, "ingest_new_runs", Mock(return_value=0))
    monkeypatch.setattr(history_routes.dashboard, "refresh", Mock(return_value=None))

    response = client.get('/health-dashboard')

    assert response.status_code == 503


@pytest.mark.parametrize("run_id", [
    "../../../etc/passwd",
    "..%2f..%2fsecrets",
    "run/../../etc",
    "run.with.dots",
])
def test_run_log_refuses_a_path_that_escapes_the_reports_root(client, run_id) -> None:
    """Le nom du run vient de l'URL : sans filtre, il servirait n'importe quel fichier."""
    response = client.get(f'/run-log/{run_id}')

    assert response.status_code == 404


def test_run_log_serves_the_log_of_a_known_run(
    monkeypatch: pytest.MonkeyPatch,
    client,
    tmp_path,
) -> None:
    """C'est la cible des liens du dashboard : sans elle, aucun graphe n'est cliquable."""
    from api.routes import history_routes

    run_dir = tmp_path / "2026_09_06-153840"
    run_dir.mkdir()
    (run_dir / "log.html").write_text("<html>journal</html>", encoding="utf-8")
    monkeypatch.setattr(history_routes.paths, "REPORTS", tmp_path)

    response = client.get('/run-log/2026_09_06-153840')

    assert response.status_code == 200
    assert b'journal' in response.data


def test_run_log_reports_a_purged_run(
    monkeypatch: pytest.MonkeyPatch,
    client,
    tmp_path,
) -> None:
    """Un run purgé reste dans les graphes du dashboard : son lien doit l'annoncer."""
    from api.routes import history_routes

    monkeypatch.setattr(history_routes.paths, "REPORTS", tmp_path)

    response = client.get('/run-log/2026_01_01-090000')

    assert response.status_code == 404
