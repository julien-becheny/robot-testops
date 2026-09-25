"""Tests unitaires du diff entre le dernier run et le dernier run comparable."""

from pathlib import Path

import pytest

from services.history import diff, store

SMOKE = "test_suites/web/00_smoke.robot::Connexion valide"
PANIER = "test_suites/web/01_cart.robot::Ajout au panier"


@pytest.fixture
def history(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Isole l'historique lu par la comparaison."""
    monkeypatch.setattr(store, "HISTORY_FILE", tmp_path / "test_history.jsonl")
    monkeypatch.setattr(store, "STATE_FILE", tmp_path / "test_history_state.json")


def _run(run_id: str, results: dict[str, str], **context) -> None:
    """Écrit un run comme le ferait l'ingestion : une entrée par test joué."""
    shared = {
        "environment": "saucedemo",
        "browser": "chromium",
        "device": "desktop",
        "workflow": "smoke",
        "commit": "aaa111",
        "run_ts": 0.0,
        **context,
    }
    store.append(
        [
            {
                **shared,
                "run_id": run_id,
                "test": test,
                "name": test.split("::")[1],
                "source": test.split("::")[0],
                "status": status,
                "elapsed_ms": 1000,
                "message": "Élément introuvable" if status == "FAIL" else "",
                "tags": [],
            }
            for test, status in results.items()
        ]
    )


def _change(report: dict, test: str) -> dict | None:
    return next((item for item in report["changes"] if item["test"] == test), None)


def test_a_test_that_stopped_passing_is_a_regression(history: None) -> None:
    """C'est le seul changement qui mérite d'interrompre quelqu'un."""
    _run("run_1", {SMOKE: "PASS"})
    _run("run_2", {SMOKE: "FAIL"}, commit="bbb222")

    report = diff.last_run_diff()

    assert report["counts"]["regression"] == 1
    assert _change(report, SMOKE)["change"] == diff.REGRESSION
    assert _change(report, SMOKE)["message"] == "Élément introuvable"


def test_a_test_left_green_is_not_reported(history: None) -> None:
    """Lister ce qui n'a pas bougé noierait ce qui a bougé."""
    _run("run_1", {SMOKE: "PASS"})
    _run("run_2", {SMOKE: "PASS"})

    assert diff.last_run_diff()["changes"] == []


def test_a_test_no_longer_played_is_never_counted_as_fixed(history: None) -> None:
    """Le pire mensonge possible : annoncer réparé un test qu'on a cessé de jouer."""
    _run("run_1", {SMOKE: "PASS", PANIER: "FAIL"})
    _run("run_2", {SMOKE: "PASS"})

    report = diff.last_run_diff()

    assert report["counts"]["fixed"] == 0
    assert _change(report, PANIER)["change"] == diff.OUT_OF_SCOPE


def test_an_ignored_test_is_treated_as_absent(history: None) -> None:
    """Un test ignoré n'a rendu aucun verdict : ni réparé, ni cassé."""
    _run("run_1", {SMOKE: "FAIL"})
    _run("run_2", {SMOKE: "SKIP"})

    report = diff.last_run_diff()

    assert report["counts"]["fixed"] == 0
    assert _change(report, SMOKE)["change"] == diff.OUT_OF_SCOPE


def test_a_run_on_another_configuration_is_not_the_reference(history: None) -> None:
    """Comparer deux périmètres différents inventerait des régressions."""
    _run("run_1", {SMOKE: "PASS", PANIER: "PASS"})
    _run("run_2", {SMOKE: "PASS"}, browser="firefox")
    _run("run_3", {SMOKE: "PASS", PANIER: "FAIL"})

    report = diff.last_run_diff()

    assert report["baseline"]["id"] == "run_1"
    assert _change(report, PANIER)["change"] == diff.REGRESSION


def test_a_narrower_workflow_is_not_compared_to_a_full_run(history: None) -> None:
    """Un smoke opposé à un run complet annoncerait un mur de faux changements."""
    _run("run_1", {SMOKE: "PASS", PANIER: "PASS"}, workflow="full")
    _run("run_2", {SMOKE: "PASS"}, workflow="smoke")
    _run("run_3", {SMOKE: "FAIL"}, workflow="smoke")

    report = diff.last_run_diff()

    assert report["baseline"]["id"] == "run_2"
    assert report["counts"]["out_of_scope"] == 0


def test_a_transition_on_a_flaky_test_is_flagged(history: None) -> None:
    """Sans ce marqueur, un test qui alterne rejouerait la même alerte à chaque run."""
    for index, status in enumerate(["PASS", "FAIL", "PASS", "FAIL", "PASS", "FAIL"]):
        _run(f"run_{index}", {SMOKE: status}, commit=f"c{index}")

    report = diff.last_run_diff()

    assert _change(report, SMOKE)["change"] == diff.REGRESSION
    assert _change(report, SMOKE)["flaky"] is True


def test_an_unchanged_failure_is_known_not_new(history: None) -> None:
    """Une dette connue ne doit pas se faire passer pour la nouvelle du jour."""
    _run("run_1", {SMOKE: "FAIL"})
    _run("run_2", {SMOKE: "FAIL"})

    report = diff.last_run_diff()

    assert report["counts"]["regression"] == 0
    assert _change(report, SMOKE)["change"] == diff.KNOWN_FAILURE


def test_a_difference_without_a_code_change_is_signalled(history: None) -> None:
    """À commit égal, la cause est ailleurs que dans le produit."""
    _run("run_1", {SMOKE: "PASS"})
    _run("run_2", {SMOKE: "FAIL"})

    assert diff.last_run_diff()["same_commit"] is True


def test_commits_are_only_equal_when_both_are_known(history: None) -> None:
    """Deux commits inconnus ne font pas un même commit."""
    _run("run_1", {SMOKE: "PASS"}, commit=None)
    _run("run_2", {SMOKE: "FAIL"}, commit=None)

    assert diff.last_run_diff()["same_commit"] is False


def test_the_first_run_of_a_configuration_has_nothing_to_compare(history: None) -> None:
    """Sans référence, annoncer un changement serait une invention."""
    _run("run_1", {SMOKE: "PASS"})

    report = diff.last_run_diff()

    assert report["baseline"] is None
    assert report["changes"] == []
    assert report["run"]["id"] == "run_1"


def test_an_empty_history_still_answers_a_complete_shape(history: None) -> None:
    """L'interface lit ces clés sans les tester une à une."""
    report = diff.last_run_diff()

    assert report == {
        "run": None,
        "baseline": None,
        "same_commit": False,
        "counts": dict.fromkeys(diff.CHANGE_ORDER, 0),
        "changes": [],
    }


def test_regressions_come_before_anything_else(history: None) -> None:
    """L'ordre de lecture décide de ce qu'on voit, donc de ce qu'on traite."""
    _run("run_1", {SMOKE: "FAIL", PANIER: "PASS"})
    _run("run_2", {SMOKE: "FAIL", PANIER: "FAIL"})

    assert [item["change"] for item in diff.last_run_diff()["changes"]] == [
        diff.REGRESSION,
        diff.KNOWN_FAILURE,
    ]
