"""Tests du contrat HTTP de la couverture fonctionnelle."""

from unittest.mock import Mock

import pytest

from api.app import app


@pytest.fixture
def client():
    """Retourne le client Flask sans démarrer de serveur réseau."""
    return app.test_client()


def test_coverage_expose_le_rapport_et_les_anomalies(
    monkeypatch: pytest.MonkeyPatch,
    client,
) -> None:
    """L'interface reçoit le rapport ET les références invalides, pour ne pas afficher un faux vert."""
    from api.routes import coverage_routes
    from services.coverage.analyzer import Finding

    rapport = {"totaux": {"ecrans": 1, "ecrans_couverts": 0}, "modules": []}
    anomalie = Finding("error", "ECRAN_INCONNU", "suite.robot:12", "écran absent du référentiel")
    monkeypatch.setattr(coverage_routes, "analyse", Mock(return_value=(rapport, [anomalie])))

    response = client.get('/coverage')

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["report"] == rapport
    assert payload["findings"] == [
        {
            "level": "error",
            "code": "ECRAN_INCONNU",
            "location": "suite.robot:12",
            "message": "écran absent du référentiel",
        }
    ]


def test_rapport_absent_renvoie_404(monkeypatch: pytest.MonkeyPatch, client) -> None:
    """Demander le rapport partageable avant de l'avoir généré ne doit pas planter."""
    from api.routes import coverage_routes

    monkeypatch.setattr(coverage_routes.paths, "RESULTS", coverage_routes.paths.TEMP / "vide")

    response = client.get('/coverage/report')

    assert response.status_code == 404
