"""Tests unitaires de la plomberie commune aux moteurs de charge."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from services.load import runner_common as common


def test_read_result_enriches_valid_json_with_exit_code(tmp_path: Path) -> None:
    """Un objet JSON valide reçoit le code de sortie du processus."""
    result_path = tmp_path / "result.json"
    result_path.write_text('{"status": "ok"}', encoding="utf-8")

    assert common.read_result(result_path, 0) == {"status": "ok", "exit_code": 0}


def test_read_result_reports_malformed_json(tmp_path: Path) -> None:
    """Un JSON mal formé produit une erreur lisible au lieu d'une exception."""
    result_path = tmp_path / "result.json"
    result_path.write_text('{"status":', encoding="utf-8")

    result = common.read_result(result_path, 1)

    assert "error" in result
    assert result["exit_code"] == 1


def test_read_result_rejects_non_object_json(tmp_path: Path) -> None:
    """Une liste JSON est refusée car le contrat du résultat exige un objet."""
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    result = common.read_result(result_path, None)

    assert "racine JSON doit être un objet" in result["error"]
    assert result["exit_code"] is None


def test_post_checks_successful_http_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un POST interne vérifie le statut HTTP avant d'annoncer son succès."""
    response = Mock()
    post = Mock(return_value=response)
    monkeypatch.setattr(common.requests, "post", post)

    assert common.post("/log", {"message": "ok"}) is True
    post.assert_called_once_with(
        f"{common.API_BASE_URL}/log",
        json={"message": "ok"},
        timeout=5,
    )
    response.raise_for_status.assert_called_once_with()


def test_post_network_error_is_best_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    """Une erreur réseau est signalée sans interrompre le workflow de charge."""
    monkeypatch.setattr(
        common.requests,
        "post",
        Mock(side_effect=requests.ConnectionError("API indisponible")),
    )

    assert common.post("/log", {"message": "ok"}) is False


def test_history_ignores_results_in_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un run sans résultat exploitable n'est pas ajouté à l'historique."""
    save_run = Mock()
    monkeypatch.setattr(common, "save_run", save_run)

    common.save_history("cible", {"label": "Cible"}, "load", {}, {"error": "échec"})

    save_run.assert_not_called()


def test_unexpected_history_error_does_not_escape(monkeypatch: pytest.MonkeyPatch) -> None:
    """Même un défaut inattendu de l'historique ne bloque pas la notification finale."""
    monkeypatch.setattr(common, "save_run", Mock(side_effect=RuntimeError("défaut inattendu")))

    common.save_history("cible", {"label": "Cible"}, "load", {}, {"status": "ok"})


def test_kill_previous_stops_running_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """L'injecteur précédent est arrêté puis retiré de la référence globale."""
    process = Mock()
    process.poll.return_value = None
    terminate = Mock()
    monkeypatch.setitem(common._ACTIVE, "proc", process)
    monkeypatch.setattr(common, "terminate", terminate)

    common.kill_previous()

    terminate.assert_called_once_with(process)
    assert common._ACTIVE["proc"] is None


def test_a_single_injector_runs_at_a_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deux moteurs simultanés fausseraient les deux mesures : le précédent est coupé."""
    previous = Mock()
    previous.poll.return_value = None
    monkeypatch.setattr(common, "terminate", Mock())
    common.remember(previous)

    common.kill_previous()
    current = Mock()
    common.remember(current)

    assert common._ACTIVE["proc"] is current


def test_local_target_shares_the_injector_machine() -> None:
    """Une cible locale est reconnue quelle que soit la forme de l'hôte."""
    assert common.is_local("http://localhost:8000") is True
    assert common.is_local("http://127.0.0.1:8000/search") is True
    assert common.is_local("https://quickpizza.grafana.com") is False
