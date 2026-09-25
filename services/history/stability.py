"""Santé de la suite : ce que l'historique dit de chaque test.

Un statut ne dit rien tout seul. Ce module transforme une succession de résultats en
verdict, et l'essentiel de son travail est de **séparer deux choses qu'on confond** : un
test qui alterne sans que le code ait bougé est fragile, un test qui échoue sans
discontinuer est cassé. Le premier se répare ou se met en quarantaine, le second révèle
un vrai défaut - les traiter pareil fait perdre des semaines.

Lecture seule : le module ne déclenche aucune ingestion, il interprète ce que
`services/history/store.py` a retenu.
"""

from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any

from services.history import store
from services.tags.parser import build_tests_list

# Fenêtre d'analyse, à ne pas confondre avec ce que le stockage conserve (plus large).
WINDOW_RUNS = 30

# En dessous, aucun verdict n'est rendu : juger la stabilité sur deux points n'a pas de sens.
MIN_RUNS_FOR_VERDICT = 5

# Une régression suivie d'un correctif produit deux alternances, et c'est légitime.
# Au-delà, l'histoire ne s'explique plus par le code.
FLIPS_FOR_DOUBT = 3

NEW = "neuf"
STABLE = "stable"
FLAKY = "instable"
BROKEN = "cassé"

# Ce qui appelle une action d'abord ; le stable n'a rien à dire.
VERDICT_ORDER = (FLAKY, BROKEN, NEW, STABLE)

# Tag qui met un test de côté sans le supprimer : il sort du verdict, pas du dépôt.
QUARANTINE_TAG = "quarantaine"

_OUTCOMES = ("PASS", "FAIL")


def suite_health(runs: int = WINDOW_RUNS) -> dict[str, Any]:
    """Retourne l'état de chaque test sur les ``runs`` derniers runs.

    Args:
        runs: Largeur de la fenêtre d'analyse, en nombre de runs.
    """
    entries = store.read_entries(runs)
    run_ids = _run_ids(entries)
    parked = _quarantined()
    grouped = _group_by_test(entries)

    tests = [_health_of(items, run_ids, parked) for items in grouped.values()]
    # Un test mis de côté avant d'avoir jamais tourné n'apparaît dans aucun run.
    tests += [
        _parked_only(meta, run_ids) for key, meta in parked.items() if key not in grouped
    ]
    tests.sort(key=_rank)

    return {
        "window": runs,
        "runs": len(run_ids),
        "counts": {
            verdict: sum(1 for test in tests if test["verdict"] == verdict)
            for verdict in VERDICT_ORDER
        },
        "quarantined": sum(1 for test in tests if test["quarantined"]),
        "tests": tests,
    }


def _run_ids(entries: list[dict]) -> list[str]:
    """Retourne les runs de la fenêtre, sans doublon, du plus ancien au plus récent."""
    seen: dict[str, None] = {}
    for entry in entries:
        run_id = entry.get("run_id")
        if isinstance(run_id, str):
            seen.setdefault(run_id, None)
    return list(seen)


def flaky_tests(runs: int = WINDOW_RUNS) -> set[str]:
    """Retourne les tests jugés instables sur les ``runs`` derniers runs.

    Plus léger que `suite_health` - pas de lecture des fichiers de test - pour qui a
    seulement besoin de savoir à qui ne pas faire confiance.

    Args:
        runs: Largeur de la fenêtre d'analyse, en nombre de runs.
    """
    grouped = _group_by_test(store.read_entries(runs))
    return {
        test
        for test, entries in grouped.items()
        if _verdict(
            [
                (entry["status"], entry.get("commit"))
                for entry in entries
                if entry.get("status") in _OUTCOMES
            ]
        )
        == FLAKY
    }


def _quarantined() -> dict[str, dict]:
    """Retourne les tests actuellement mis de côté, lus dans les fichiers de test.

    L'historique ne peut pas le savoir : le tag est posé **après** le dernier run, et un
    test en quarantaine ne tourne plus - il ne produirait donc plus jamais d'entrée.
    """
    parked = {}
    for test in build_tests_list():
        if QUARANTINE_TAG not in {tag.lower() for tag in test.get("tags", [])}:
            continue
        source = Path(test["file"]).as_posix()
        key = f"{source}::{test['name']}"
        parked[key] = {
            "test": key,
            "name": test["name"],
            "source": source,
            "tags": test.get("tags", []),
        }
    return parked


def _group_by_test(entries: list[dict]) -> dict[str, list[dict]]:
    """Regroupe les entrées par test, en conservant l'ordre chronologique."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for entry in entries:
        name = entry.get("test")
        if name:
            grouped[name].append(entry)
    return grouped


def _health_of(entries: list[dict], run_ids: list[str], parked: dict[str, dict]) -> dict[str, Any]:
    """Résume l'histoire d'un test : ce qu'il a donné, combien de temps, et le verdict."""
    latest = entries[-1]
    outcomes = [
        (entry["status"], entry.get("commit"))
        for entry in entries
        if entry.get("status") in _OUTCOMES
    ]
    statuses = [status for status, _commit in outcomes]
    durations = [
        entry["elapsed_ms"] for entry in entries if isinstance(entry.get("elapsed_ms"), int)
    ]
    return {
        "test": latest["test"],
        "name": latest.get("name"),
        "source": latest.get("source"),
        "tags": latest.get("tags", []),
        "runs": len(entries),
        "passed": statuses.count("PASS"),
        "failed": statuses.count("FAIL"),
        "skipped": len(entries) - len(outcomes),
        "pass_rate": statuses.count("PASS") / len(statuses) if statuses else None,
        "last_status": latest.get("status"),
        "last_message": _last_failure_message(entries),
        "statuses": [entry.get("status") for entry in entries],
        "median_ms": round(median(durations)) if durations else None,
        "flips": _flips(statuses),
        "verdict": _verdict(outcomes),
        "quarantined": latest["test"] in parked,
        "runs_since": _runs_since(latest.get("run_id"), run_ids),
    }


def _parked_only(meta: dict, run_ids: list[str]) -> dict[str, Any]:
    """Décrit un test mis de côté dont la fenêtre ne garde aucune trace."""
    return {
        **meta,
        "runs": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "pass_rate": None,
        "last_status": None,
        "last_message": None,
        "statuses": [],
        "median_ms": None,
        "flips": 0,
        "verdict": NEW,
        "quarantined": True,
        "runs_since": len(run_ids),
    }


def _runs_since(last_run_id: str | None, run_ids: list[str]) -> int:
    """Compte les runs joués depuis la dernière exécution du test.

    C'est le garde-fou du cimetière : une quarantaine qu'on oublie se voit à ce nombre.
    """
    if last_run_id in run_ids:
        return len(run_ids) - 1 - run_ids.index(last_run_id)
    return len(run_ids)


def _verdict(outcomes: list[tuple[str, str | None]]) -> str:
    """Qualifie un test d'après la suite de ses résultats et les commits associés."""
    if len(outcomes) < MIN_RUNS_FOR_VERDICT:
        return NEW

    statuses = [status for status, _commit in outcomes]
    if _alternates_on_one_commit(outcomes) or _flips(statuses) >= FLIPS_FOR_DOUBT:
        return FLAKY
    if "PASS" not in statuses:
        return BROKEN
    return STABLE


def _alternates_on_one_commit(outcomes: list[tuple[str, str | None]]) -> bool:
    """Dit si le test a donné deux verdicts différents sans que le code ait bougé.

    C'est la seule preuve directe de fragilité : à commit égal, seul le test peut
    expliquer la différence. Les résultats sans commit connu sont écartés - deux
    inconnus ne font pas un même commit.
    """
    per_commit: dict[str, set[str]] = defaultdict(set)
    for status, commit in outcomes:
        if commit:
            per_commit[commit].add(status)
    return any(len(statuses) > 1 for statuses in per_commit.values())


def _flips(statuses: list[str]) -> int:
    """Compte les changements de verdict d'un résultat au suivant."""
    return sum(
        1 for before, after in zip(statuses, statuses[1:], strict=False) if before != after
    )


def _last_failure_message(entries: list[dict]) -> str | None:
    """Retourne le message du dernier échec, ou None si le test n'a jamais échoué."""
    for entry in reversed(entries):
        if entry.get("status") == "FAIL" and entry.get("message"):
            return entry["message"]
    return None


def _rank(test: dict[str, Any]) -> tuple:
    """Ordonne les tests par urgence : le verdict d'abord, le taux de réussite ensuite.

    Un test en quarantaine passe en dernier : il ne tourne plus, donc il n'appelle aucune
    action immédiate - seulement une relecture périodique.
    """
    pass_rate = test["pass_rate"] if test["pass_rate"] is not None else 1.0
    return (
        test["quarantined"],
        VERDICT_ORDER.index(test["verdict"]),
        pass_rate,
        test["test"],
    )
