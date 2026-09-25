"""Écrans de suivi d'un test de charge : dashboard annoncé et rapport k6 servi."""

from pathlib import Path

import pytest

from api.app import app
from api.routes import load_routes


@pytest.fixture
def report_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Isole le dossier des rapports de charge et rend un client Flask."""
    monkeypatch.setattr(load_routes.k6_runner, "REPORTS_DIR", tmp_path)
    return app.test_client(), tmp_path


def test_k6_report_is_served_after_the_run(report_client) -> None:
    """Le rapport HTML survit au run : c'est tout l'intérêt de l'exporter."""
    client, report_dir = report_client
    (report_dir / "k6_abc123.html").write_text("<html>courbes</html>", encoding="utf-8")

    response = client.get("/load-report/k6_abc123.html")

    assert response.status_code == 200
    assert "courbes" in response.get_data(as_text=True)


def test_report_of_a_purged_run_is_a_clear_404(report_client) -> None:
    """Un rapport effacé donne un message, pas une erreur serveur."""
    client, _ = report_client

    response = client.get("/load-report/k6_deadbeef.html")

    assert response.status_code == 404
    assert "introuvable" in response.get_json()["error"]


@pytest.mark.parametrize("name", [
    "../../../etc/passwd",
    "..%2f..%2fconfig%2fvariables_config.json",
    "k6_abc123.html.bak",
    "rapport.html",
])
def test_only_generated_report_names_are_accepted(report_client, name: str) -> None:
    """Le nom vient du runner : tout le reste est une tentative de sortir du dossier."""
    client, report_dir = report_client
    (report_dir / "k6_abc123.html").write_text("<html></html>", encoding="utf-8")

    response = client.get(f"/load-report/{name}")

    assert response.status_code == 404
    assert "courbes" not in response.get_data(as_text=True)


def test_run_load_announces_the_dashboard_of_both_engines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """k6 a désormais son écran temps réel, comme Locust : l'URL ne peut plus être nulle."""
    monkeypatch.setattr(load_routes, "_RUNNERS", {
        "locust": lambda *args: None,
        "k6": lambda *args: None,
    })
    client = app.test_client()

    for test_type, engine in (("load", "locust"), ("open_load", "k6")):
        response = client.post("/run-load", json={
            "target": "quickpizza", "test_type": test_type, "params": {},
        })

        body = response.get_json()
        assert response.status_code == 200, body
        assert body["engine"] == engine
        assert body["dashboard_url"].startswith("http://localhost:")
