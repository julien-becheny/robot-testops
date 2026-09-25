"""Tests unitaires des verdicts de stabilité."""

from pathlib import Path

import pytest

from services.history import stability, store


@pytest.fixture
def history(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Isole l'historique lu par l'analyse et part sans aucun test en quarantaine."""
    monkeypatch.setattr(store, "HISTORY_FILE", tmp_path / "test_history.jsonl")
    monkeypatch.setattr(store, "STATE_FILE", tmp_path / "test_history_state.json")
    monkeypatch.setattr(stability, "build_tests_list", lambda: [])


def _quarantine(monkeypatch: pytest.MonkeyPatch, *keys: str) -> None:
    """Simule des tests portant le tag de quarantaine dans les fichiers de test."""
    declared = []
    for key in keys:
        source, name = key.split("::")
        declared.append(
            {"name": name, "file": source, "tags": ["smoke", stability.QUARANTINE_TAG]}
        )
    monkeypatch.setattr(stability, "build_tests_list", lambda: declared)


def _record(
    statuses: list[str],
    test: str = "test_suites/web/00_smoke.robot::Connexion valide",
    commits: list[str] | None = None,
    durations: list[int] | None = None,
    message: str = "Élément introuvable",
) -> None:
    """Écrit un run par statut, comme le ferait l'ingestion."""
    source, name = test.split("::")
    for index, status in enumerate(statuses):
        store.append(
            [
                {
                    "run_id": f"run_{index}",
                    "test": test,
                    "name": name,
                    "source": source,
                    "tags": ["smoke"],
                    "status": status,
                    "elapsed_ms": durations[index] if durations else 1000,
                    "message": message if status == "FAIL" else "",
                    "commit": commits[index] if commits else None,
                }
            ]
        )


def _test_named(
    health: dict, name: str = "test_suites/web/00_smoke.robot::Connexion valide"
) -> dict:
    return next(item for item in health["tests"] if item["test"] == name)


def test_no_verdict_is_given_on_too_few_runs(history: None) -> None:
    """Juger la stabilité sur deux points n'aurait aucune valeur."""
    _record(["PASS", "FAIL"])

    assert _test_named(stability.suite_health())["verdict"] == stability.NEW


def test_a_test_that_always_passes_is_stable(history: None) -> None:
    """Le cas nominal ne doit rien réclamer."""
    _record(["PASS"] * 6)

    health = _test_named(stability.suite_health())
    assert health["verdict"] == stability.STABLE
    assert health["pass_rate"] == 1.0
    assert health["passed"] == 6
    assert health["statuses"] == ["PASS"] * 6


def test_a_test_that_never_passes_is_broken_not_flaky(history: None) -> None:
    """Un échec systématique n'est pas de la fragilité : c'est un défaut à corriger."""
    _record(["FAIL"] * 6)

    health = _test_named(stability.suite_health())
    assert health["verdict"] == stability.BROKEN
    assert health["last_message"] == "Élément introuvable"


def test_alternating_on_the_same_commit_proves_flakiness(history: None) -> None:
    """À code égal, seule le test peut expliquer deux verdicts différents."""
    _record(
        ["PASS", "PASS", "FAIL", "PASS", "PASS", "PASS"],
        commits=["a1b2c3d"] * 6,
    )

    assert _test_named(stability.suite_health())["verdict"] == stability.FLAKY


def test_a_regression_then_a_fix_is_not_flakiness(history: None) -> None:
    """Le piège : rouge puis vert sur des commits différents raconte une correction."""
    _record(
        ["PASS", "PASS", "FAIL", "FAIL", "PASS", "PASS"],
        commits=["aaa", "aaa", "bbb", "bbb", "ccc", "ccc"],
    )

    assert _test_named(stability.suite_health())["verdict"] == stability.STABLE


def test_repeated_alternation_raises_doubt_even_without_commits(history: None) -> None:
    """Les runs antérieurs à la carte d'identité n'ont pas de commit : la forme suffit."""
    _record(["PASS", "FAIL", "PASS", "FAIL", "PASS", "FAIL"])

    health = _test_named(stability.suite_health())
    assert health["verdict"] == stability.FLAKY
    assert health["flips"] == 5


def test_skipped_runs_do_not_count_in_the_pass_rate(history: None) -> None:
    """Un test ignoré n'a rien prouvé, ni dans un sens ni dans l'autre."""
    _record(["PASS", "PASS", "SKIP", "PASS", "PASS", "PASS"])

    health = _test_named(stability.suite_health())
    assert health["skipped"] == 1
    assert health["passed"] == 5
    assert health["pass_rate"] == 1.0


def test_duration_is_summarised_by_its_median(history: None) -> None:
    """La médiane résiste au run anormalement lent, contrairement à la moyenne."""
    _record(["PASS"] * 5, durations=[1000, 1100, 1200, 1300, 30000])

    assert _test_named(stability.suite_health())["median_ms"] == 1200


def test_tests_needing_action_come_first(history: None) -> None:
    """Le stable n'a rien à dire : il ne doit pas occuper le haut de la liste."""
    _record(["PASS"] * 6, test="suite.robot::Stable")
    _record(["FAIL"] * 6, test="suite.robot::Cassé")
    _record(["PASS", "FAIL", "PASS", "FAIL", "PASS", "FAIL"], test="suite.robot::Instable")

    health = stability.suite_health()

    assert [item["test"] for item in health["tests"]] == [
        "suite.robot::Instable",
        "suite.robot::Cassé",
        "suite.robot::Stable",
    ]
    assert health["counts"] == {
        stability.FLAKY: 1,
        stability.BROKEN: 1,
        stability.NEW: 0,
        stability.STABLE: 1,
    }


def test_an_empty_history_produces_an_empty_report(history: None) -> None:
    """Avant le premier run, l'analyse répond sans inventer."""
    health = stability.suite_health()

    assert health["tests"] == []
    assert health["runs"] == 0


def test_a_quarantined_test_is_flagged_and_ranked_last(
    monkeypatch: pytest.MonkeyPatch,
    history: None,
) -> None:
    """Mis de côté, il ne tourne plus : il n'appelle plus d'action immédiate."""
    _record(["PASS", "FAIL", "PASS", "FAIL", "PASS", "FAIL"], test="suite.robot::Instable")
    _record(["PASS"] * 6, test="suite.robot::Stable")
    _quarantine(monkeypatch, "suite.robot::Instable")

    health = stability.suite_health()

    assert [item["test"] for item in health["tests"]] == [
        "suite.robot::Stable",
        "suite.robot::Instable",
    ]
    assert health["quarantined"] == 1


def test_a_quarantined_test_without_history_is_still_listed(
    monkeypatch: pytest.MonkeyPatch,
    history: None,
) -> None:
    """Sans cela, un test mis de côté disparaîtrait de la vue : la quarantaine deviendrait un cimetière."""
    _record(["PASS"] * 6, test="suite.robot::Stable")
    _quarantine(monkeypatch, "suite.robot::Oublié")

    health = stability.suite_health()
    parked = _test_named(health, "suite.robot::Oublié")

    assert parked["runs"] == 0
    assert parked["verdict"] == stability.NEW
    assert parked["runs_since"] == 6


def test_runs_since_counts_the_runs_played_without_this_test(history: None) -> None:
    """Un test qui ne tourne plus doit se voir, même sans être en quarantaine."""
    _record(["PASS"] * 6, test="suite.robot::Actif")
    _record(["PASS", "PASS"], test="suite.robot::Delaisse")

    health = stability.suite_health()

    assert _test_named(health, "suite.robot::Actif")["runs_since"] == 0
    assert _test_named(health, "suite.robot::Delaisse")["runs_since"] == 4
