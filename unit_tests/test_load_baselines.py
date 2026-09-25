"""Tests de la reference de comparaison et de la detection de regression."""

import json

import pytest

from services.load import analysis, baselines


@pytest.fixture(autouse=True)
def _fichier_isole(tmp_path, monkeypatch):
    """Ecrit dans un dossier temporaire : jamais dans les references reelles."""
    monkeypatch.setattr(baselines, "BASELINES_FILE", tmp_path / "load_baselines.json")


def _run(**result_fields):
    result = {"p95_ms": 480, "reqs_per_sec": 12.0, "p50_ms": 130, "error_rate": 0.0}
    result.update(result_fields)
    return {
        "id": "abc123", "ts": 1_700_000_000.0, "target": "cible_demo",
        "target_label": "Cible de demo", "test_type": "load",
        "params": {"vus": 12, "steady": "2m", "p95_ms": 800},
        "result": result,
    }


def test_a_baseline_survives_the_history_being_trimmed() -> None:
    """L'historique est borne : une reference qui n'y pointerait que par identifiant
    finirait par designer un run efface."""
    baselines.set_baseline(_run())

    reference = baselines.get("cible_demo", "load")

    assert reference["metrics"]["p95_ms"] == 480
    assert reference["run_id"] == "abc123"


def test_thresholds_do_not_make_two_runs_incomparable() -> None:
    """Resserrer un seuil ne change pas la charge appliquee : la comparaison reste valide."""
    baselines.set_baseline(_run())
    reference = baselines.get("cible_demo", "load")

    ecart = baselines.compare({"p95_ms": 490}, {"vus": 12, "steady": "2m", "p95_ms": 500},
                              reference)

    assert ecart["comparable"] is True


def test_a_different_load_is_flagged_as_not_comparable() -> None:
    """Comparer 12 et 30 utilisateurs mesurerait le reglage, pas le systeme."""
    baselines.set_baseline(_run())
    reference = baselines.get("cible_demo", "load")

    ecart = baselines.compare({"p95_ms": 900}, {"vus": 30, "steady": "2m"}, reference)

    assert ecart["comparable"] is False


def test_a_real_regression_is_raised_as_critical() -> None:
    """Le cas d'usage : une version livree degrade le p95 a charge identique."""
    result = {"p95_ms": 610, "reqs_per_sec": 12.0, "baseline": {
        "comparable": True,
        "deltas": {"p95_ms": {"avant": 480, "apres": 610, "pct": 27.1},
                   "reqs_per_sec": {"avant": 12.0, "apres": 12.0, "pct": 0.0}},
    }}

    findings = analysis.analyze(result, {"p95_ms": 800}, "load")
    finding = next(f for f in findings if "référence" in f["title"])

    assert finding["level"] == "crit"
    assert "Régression" in finding["title"]
    assert "+27 %" in finding["title"]


def test_an_improvement_invites_to_check_the_scenario() -> None:
    """Un gain inexplique est aussi suspect qu'une perte : le scenario teste-t-il encore ?"""
    result = {"p95_ms": 240, "baseline": {
        "comparable": True,
        "deltas": {"p95_ms": {"avant": 480, "apres": 240, "pct": -50.0}},
    }}

    findings = analysis.analyze(result, {"p95_ms": 800}, "load")
    finding = next(f for f in findings if "référence" in f["title"])

    assert finding["level"] == "good"
    assert "teste toujours la même chose" in finding["detail"]


def test_measurement_noise_is_not_reported_as_a_regression() -> None:
    """Deux runs identiques se sont tenus a 2 % pres : alerter la rendrait l'alerte inutile."""
    result = {"p95_ms": 492, "baseline": {
        "comparable": True,
        "deltas": {"p95_ms": {"avant": 480, "apres": 492, "pct": 2.5}},
    }}

    findings = analysis.analyze(result, {"p95_ms": 800}, "load")
    finding = next(f for f in findings if "référence" in f["title"])

    assert finding["level"] == "info"
    assert "Conforme" in finding["title"]


def test_a_failed_run_never_becomes_a_reference() -> None:
    baselines.set_baseline(_run(error="k6 introuvable"))

    assert baselines.get("cible_demo", "load") is None


def test_clearing_a_reference_leaves_the_others_alone() -> None:
    baselines.set_baseline(_run())
    autre = _run()
    autre["test_type"] = "capacity"
    baselines.set_baseline(autre)

    assert baselines.clear("cible_demo", "load") is True
    assert baselines.get("cible_demo", "load") is None
    assert baselines.get("cible_demo", "capacity") is not None
    assert json.loads(baselines.BASELINES_FILE.read_text(encoding="utf-8"))


def test_the_breaking_point_is_what_a_capacity_run_compares() -> None:
    """Cas reel : p95 +8,5 % alors que la capacite avait progresse.

    Deux capacity aux memes reglages s'arretent a des paliers differents, donc leurs
    percentiles n'agregent pas la meme population. Comparer les p95 se lit a l'envers.
    """
    avant = _run(p95_ms=710, reqs_per_sec=65.1)
    avant["result"]["breach"] = {"users": 140, "rps": 78.7, "p95_ms": 810, "t": 500.0}
    avant["test_type"] = "capacity"
    baselines.set_baseline(avant)

    apres = {"p95_ms": 770, "reqs_per_sec": 71.1,
             "breach": {"users": 160, "rps": 86.7, "p95_ms": 830, "t": 600.0,
                        "error_rate": 0.0},
             "baseline": None}
    apres["baseline"] = baselines.compare(apres, avant["params"],
                                          baselines.get("cible_demo", "capacity"))

    findings = analysis.analyze(apres, {"p95_ms": 800}, "capacity")
    finding = next(f for f in findings if "apacité " in f["title"])

    # Un seul palier d'ecart (pas de 20 VUs) : c'est la resolution de la mesure.
    assert finding["level"] == "info"
    assert "Capacité stable" in finding["title"]
    # Le p95 en hausse ne doit jamais etre presente comme une regression.
    assert not any("Régression" in f["title"] for f in findings)


def test_a_clear_capacity_gain_is_celebrated() -> None:
    """Cas reel : un index fait passer la capacite de 20 a 140 utilisateurs."""
    avant = _run(p95_ms=640, reqs_per_sec=8.9)
    avant["result"]["breach"] = {"users": 20, "rps": 12.0, "p95_ms": 810, "t": 136.0}
    avant["test_type"] = "capacity"
    baselines.set_baseline(avant)

    apres = {"p95_ms": 710, "reqs_per_sec": 65.1,
             "breach": {"users": 140, "rps": 78.7, "p95_ms": 810, "t": 500.0}}
    apres["baseline"] = baselines.compare(apres, avant["params"],
                                          baselines.get("cible_demo", "capacity"))

    findings = analysis.analyze(apres, {"p95_ms": 800}, "capacity")
    finding = next(f for f in findings if "apacité " in f["title"])

    assert finding["level"] == "good"
    assert "Capacité en hausse" in finding["title"]
    assert "+600 %" in finding["title"]


def test_a_capacity_that_breaks_earlier_is_a_real_regression() -> None:
    avant = _run()
    avant["result"]["breach"] = {"users": 160, "rps": 86.7, "p95_ms": 830, "t": 600.0}
    avant["test_type"] = "capacity"
    baselines.set_baseline(avant)

    apres = {"breach": {"users": 100, "rps": 55.0, "p95_ms": 810, "t": 300.0}}
    apres["baseline"] = baselines.compare(apres, avant["params"],
                                          baselines.get("cible_demo", "capacity"))

    findings = analysis.analyze(apres, {}, "capacity")
    finding = next(f for f in findings if "apacité " in f["title"])

    assert finding["level"] == "crit"
    assert "Capacité en baisse" in finding["title"]


def test_the_interface_can_tell_which_runs_are_pinned() -> None:
    """Sans cette liste, les drapeaux dispara\u00eetraient au rafra\u00eechissement de la page."""
    baselines.set_baseline(_run())

    toutes = baselines.list_all()

    assert [r["run_id"] for r in toutes.values()] == ["abc123"]


def test_pinning_a_new_run_replaces_the_previous_reference() -> None:
    """Un couple cible/type n'a qu'une r\u00e9f\u00e9rence : deux en concurrence n'auraient pas de sens."""
    baselines.set_baseline(_run())
    recent = _run()
    recent["id"] = "def456"
    baselines.set_baseline(recent)

    assert baselines.get("cible_demo", "load")["run_id"] == "def456"
    assert len(baselines.list_all()) == 1
