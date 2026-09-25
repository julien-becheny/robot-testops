"""Tests unitaires du runner k6 sans lancer de processus de charge."""

from pathlib import Path
from unittest.mock import Mock

import psutil
import pytest
import requests

from services.load import k6_runner


def test_first_sample_uses_the_whole_run_as_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sans relevé précédent, le débit se calcule sur le temps déjà écoulé."""
    monkeypatch.setattr(k6_runner, "_metrics", lambda _url: {
        "http_reqs": {"count": 200}, "vus": {"value": 12},
        "http_req_duration": {"p(95)": 320.4}, "http_req_failed": {"rate": 0},
    })

    sample = k6_runner._sample("http://api", 10.0, None)

    assert sample["rps"] == 20.0
    assert sample["users"] == 12
    assert sample["p95_ms"] == 320


def test_next_sample_measures_the_instant_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    """k6 ne publie que des cumuls : le débit courant vient de l'écart entre deux relevés."""
    monkeypatch.setattr(k6_runner, "_metrics", lambda _url: {
        "http_reqs": {"count": 260}, "vus": {"value": 20},
        "http_req_duration": {"p(95)": 500}, "http_req_failed": {"rate": 0.02},
        "dropped_iterations": {"count": 45},
    })
    previous = {"t": 10.0, "reqs": 200}

    sample = k6_runner._sample("http://api", 12.0, previous)

    assert sample["rps"] == 30.0  # 60 requêtes en 2 s, et non 260/12
    assert sample["dropped"] == 45
    assert sample["error_rate"] == 0.02


def test_sample_is_skipped_when_the_api_says_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Une API muette ne produit pas de point : mieux vaut un trou qu'un zéro inventé."""
    monkeypatch.setattr(k6_runner, "_metrics", lambda _url: {})

    assert k6_runner._sample("http://api", 4.0, None) is None


def test_metrics_flattens_the_json_api_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """Les métriques k6 arrivent au format JSON:API et sont ramenées à un dict simple."""
    response = Mock()
    response.json.return_value = {"data": [
        {"id": "http_reqs", "attributes": {"type": "counter", "sample": {"count": 7}}},
        {"id": "vus", "attributes": {"type": "gauge", "sample": {"value": 3}}},
    ]}
    monkeypatch.setattr(k6_runner.requests, "get", Mock(return_value=response))

    metrics = k6_runner._metrics("http://api")

    assert metrics["http_reqs"]["count"] == 7
    assert metrics["vus"]["value"] == 3


def test_unreachable_metrics_api_does_not_break_the_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le direct est un confort : son indisponibilité ne doit pas interrompre la charge."""
    monkeypatch.setattr(
        k6_runner.requests, "get", Mock(side_effect=requests.ConnectionError("k6 muet")))

    assert k6_runner._metrics("http://api") == {}


def test_manual_stop_asks_k6_to_finish_properly(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tuer le processus sauterait handleSummary : l'arrêt passe par l'API REST."""
    response = Mock()
    patch = Mock(return_value=response)
    monkeypatch.setattr(k6_runner.requests, "patch", patch)

    assert k6_runner._request_stop("http://api") is True
    assert patch.call_args.args[0] == "http://api/v1/status"
    assert patch.call_args.kwargs["json"]["data"]["attributes"] == {"stopped": True}


def test_failed_stop_request_is_reported_not_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si l'API ne répond pas, le runner enchaîne sur l'arrêt brutal sans exploser."""
    monkeypatch.setattr(
        k6_runner.requests, "patch", Mock(side_effect=requests.ConnectionError("k6 muet")))

    assert k6_runner._request_stop("http://api") is False


def test_injector_cpu_is_a_share_of_the_whole_machine(monkeypatch: pytest.MonkeyPatch) -> None:
    """400 % sur 16 coeurs = 25 % de la machine : le seuil de 90 % garde le sens de Locust."""
    process = Mock()
    process.cpu_percent.side_effect = [0.0, 400.0]
    monkeypatch.setattr(k6_runner.psutil, "Process", Mock(return_value=process))
    monkeypatch.setattr(k6_runner.os, "cpu_count", lambda: 16)

    assert k6_runner._cpu_meter(Mock(pid=123))() == 25.0


def test_unmeasurable_cpu_never_interrupts_the_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un processus déjà terminé rend un relève-compteur muet, pas une exception."""
    monkeypatch.setattr(
        k6_runner.psutil, "Process", Mock(side_effect=psutil.NoSuchProcess(123)))

    assert k6_runner._cpu_meter(Mock(pid=123))() is None


def test_export_is_awaited_until_the_report_stops_growing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """k6 crée le fichier avant de le remplir : couper au premier octet le tronquerait."""
    sizes = iter([0, 120_000, 165_000, 165_000])
    monkeypatch.setattr(k6_runner, "_size", lambda _path: next(sizes))
    monkeypatch.setattr(k6_runner.time, "sleep", lambda _seconds: None)

    assert k6_runner._wait_for_export(tmp_path / "k6_run.html", seconds=30) is True


def test_missing_export_does_not_advertise_a_report(tmp_path: Path) -> None:
    """Sans rapport écrit, aucun lien ne doit être proposé à l'utilisateur."""
    assert k6_runner._wait_for_export(tmp_path / "absent.html", seconds=0) is False


def test_status_separates_a_finished_test_from_a_running_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le processus survit au test : seul le statut dit lequel des deux est fini."""
    response = Mock()
    response.json.return_value = {"data": {"attributes": {"running": False}}}
    monkeypatch.setattr(k6_runner.requests, "get", Mock(return_value=response))

    assert k6_runner._is_running("http://api") is False


def test_unreachable_status_concludes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Une API muette ne doit pas passer pour un test terminé."""
    monkeypatch.setattr(
        k6_runner.requests, "get", Mock(side_effect=requests.ConnectionError("k6 muet")))

    assert k6_runner._is_running("http://api") is None


def _follow_context(monkeypatch: pytest.MonkeyPatch, statuses: list[bool | None]) -> dict:
    """Prépare un suivi de run sans attente réelle et capture ce qui est publié."""
    published: dict = {"logs": [], "metrics": [], "sleeps": 0}
    monkeypatch.setattr(k6_runner, "_metrics", lambda _url: {
        "http_reqs": {"count": 10}, "vus": {"value": 0},
        "http_req_duration": {"p(95)": 50}, "http_req_failed": {"rate": 0},
    })
    monkeypatch.setattr(k6_runner, "_is_running", Mock(side_effect=statuses))
    monkeypatch.setattr(k6_runner, "_cpu_meter", lambda _proc: lambda: None)
    monkeypatch.setattr(k6_runner.common, "emit_log",
                        lambda _sid, message: published["logs"].append(message))
    monkeypatch.setattr(k6_runner.common, "emit_metrics",
                        lambda _sid, metrics: published["metrics"].append(metrics))
    return published


def test_finished_test_triggers_the_dashboard_closing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Un onglet ouvert retient le résumé : TestOps demande sa fermeture, puis l'obtient."""
    result_path, stop_path = tmp_path / "result.json", tmp_path / "stop.txt"
    published = _follow_context(monkeypatch, [True, False])

    def write_result_on_third_tick(_seconds: float) -> None:
        published["sleeps"] += 1
        if published["sleeps"] == 3:
            result_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(k6_runner.time, "sleep", write_result_on_third_tick)
    proc = Mock()
    proc.poll.return_value = None

    outcome = k6_runner._follow(proc, "http://api", "sid", result_path, stop_path,
                                {"timeline": [], "breach": None, "cpu_max": 0.0}, "open_load")

    assert outcome == "done"
    assert published["metrics"][-1] == {"finished": True}
    assert any("dashboard" in message for message in published["logs"])


def test_dashboard_left_open_forever_ends_the_run_with_an_explanation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Personne ne fermera l'onglet : le run se termine au lieu d'attendre indéfiniment."""
    published = _follow_context(monkeypatch, [True, False])
    monkeypatch.setattr(k6_runner.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(k6_runner, "DASHBOARD_GRACE_S", 0)
    proc = Mock()
    proc.poll.return_value = None

    outcome = k6_runner._follow(proc, "http://api", "sid", tmp_path / "absent.json",
                                tmp_path / "stop.txt",
                                {"timeline": [], "breach": None, "cpu_max": 0.0}, "open_load")

    assert outcome == "abandoned"
    assert published["metrics"][-1] == {"finished": True}

