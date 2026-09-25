"""Ce qui a changé depuis le dernier run comparable.

« 12/14 réussis » ne dit pas si les deux rouges sont tombés ce matin ou traînent depuis
trois semaines. Ce module répond à l'autre question - **qu'est-ce qui a bougé** - et
réserve l'alerte aux tests qui passaient et ne passent plus.

Trois précautions font tout l'intérêt du résultat :

- **Comparable, pas précédent.** Le run d'avant peut viser un autre environnement, un
  autre navigateur ou un autre périmètre. La référence est le dernier run de même clé,
  pas le dernier run tout court.
- **Un test absent n'est pas un test réparé.** Un test filtré par les tags, ignoré ou
  supprimé sort du périmètre ; le compter comme réparé serait le pire mensonge que cet
  outil puisse produire.
- **Une alternance n'est pas une régression.** Un test que `stability` juge instable
  bascule sans que rien n'ait changé : sa transition est signalée à part, sinon chaque
  run rejouerait la même fausse alerte - exactement la fatigue d'alerte qu'on veut fuir.

Lecture seule : le module n'ingère rien, il interprète ce que
`services/history/store.py` a retenu.
"""

from typing import Any

from services.history import store
from services.history.stability import flaky_tests

# Jusqu'où remonter pour retrouver un run de même périmètre. Au-delà, la référence
# serait si ancienne que « ce qui a changé » ne voudrait plus dire grand-chose.
LOOKBACK_RUNS = 30

REGRESSION = "regression"
FIXED = "fixed"
KNOWN_FAILURE = "known_failure"
NEW = "new"
OUT_OF_SCOPE = "out_of_scope"

# Ce qui appelle une action d'abord ; un échec déjà connu n'apprend rien de neuf.
CHANGE_ORDER = (REGRESSION, FIXED, NEW, KNOWN_FAILURE, OUT_OF_SCOPE)

# Un test ignoré n'a rendu aucun verdict : on le traite comme absent plutôt que comme
# un troisième statut, ce qui éviterait de le confondre avec une réparation.
_OUTCOMES = ("PASS", "FAIL")


def last_run_diff(lookback: int = LOOKBACK_RUNS) -> dict[str, Any]:
    """Compare le dernier run au dernier run de même périmètre.

    Args:
        lookback: Nombre de runs remontés pour chercher une référence.

    Returns:
        Le contexte des deux runs, le décompte par nature de changement et le détail
        test par test. ``baseline`` vaut None quand cette configuration n'a jamais
        tourné auparavant : il n'y a alors rien à comparer, et rien à annoncer.
    """
    runs = _split_runs(store.read_entries(lookback))
    if not runs:
        return _nothing_to_compare(None)

    current = runs[-1]
    context = _context(current)
    baseline = _previous_comparable(runs[:-1], _scope(context))
    if baseline is None:
        return _nothing_to_compare(context)

    reference = _context(baseline)
    changes = _changes(_outcomes(baseline), _outcomes(current), flaky_tests(lookback))
    return {
        "run": context,
        "baseline": reference,
        # À code identique, une différence ne vient pas du produit mais de
        # l'environnement, de la donnée ou du test lui-même.
        "same_commit": bool(context["commit"]) and context["commit"] == reference["commit"],
        "counts": _counts(changes),
        "changes": changes,
    }


def _nothing_to_compare(context: dict | None) -> dict[str, Any]:
    """Retourne un résultat vide mais complet, pour un appelant qui n'a rien à afficher."""
    return {
        "run": context,
        "baseline": None,
        "same_commit": False,
        "counts": _counts([]),
        "changes": [],
    }


def _split_runs(entries: list[dict]) -> list[list[dict]]:
    """Regroupe les entrées par run, du plus ancien au plus récent."""
    runs: dict[str, list[dict]] = {}
    for entry in entries:
        run_id = entry.get("run_id")
        if isinstance(run_id, str):
            runs.setdefault(run_id, []).append(entry)
    return list(runs.values())


def _context(entries: list[dict]) -> dict[str, Any]:
    """Extrait la carte d'identité d'un run, répétée à l'identique sur chacune de ses lignes."""
    first = entries[0]
    return {
        "id": first.get("run_id"),
        "ts": first.get("run_ts"),
        "commit": first.get("commit"),
        "environment": first.get("environment"),
        "browser": first.get("browser"),
        "device": first.get("device"),
        "workflow": first.get("workflow"),
    }


def _scope(context: dict) -> tuple:
    """Retourne ce qui doit concorder pour que deux runs soient opposables."""
    return (
        context["environment"],
        context["browser"],
        context["device"],
        context["workflow"],
    )


def _previous_comparable(older: list[list[dict]], scope: tuple) -> list[dict] | None:
    """Retourne le run de même périmètre le plus récent, ou None s'il n'y en a aucun."""
    for entries in reversed(older):
        if _scope(_context(entries)) == scope:
            return entries
    return None


def _outcomes(entries: list[dict]) -> dict[str, dict]:
    """Indexe par test les résultats qui portent un verdict."""
    return {
        entry["test"]: entry
        for entry in entries
        if entry.get("test") and entry.get("status") in _OUTCOMES
    }


def _changes(before: dict[str, dict], after: dict[str, dict], flaky: set[str]) -> list[dict]:
    """Qualifie chaque test des deux runs, en écartant ceux qui n'ont rien à dire."""
    changes = []
    for test in sorted(before.keys() | after.keys()):
        previous, current = before.get(test), after.get(test)
        kind = _classify(previous, current)
        if kind is None:
            continue
        known = current or previous
        changes.append({
            "test": test,
            "name": known.get("name"),
            "source": known.get("source"),
            "change": kind,
            "status": current.get("status") if current else None,
            "previous_status": previous.get("status") if previous else None,
            "message": current.get("message") if current else None,
            "flaky": test in flaky,
        })
    changes.sort(key=_rank)
    return changes


def _classify(previous: dict | None, current: dict | None) -> str | None:
    """Nomme la transition d'un test, ou None quand il est resté vert."""
    if previous is None:
        return NEW
    if current is None:
        return OUT_OF_SCOPE
    if previous["status"] == "PASS" and current["status"] == "FAIL":
        return REGRESSION
    if previous["status"] == "FAIL" and current["status"] == "PASS":
        return FIXED
    if current["status"] == "FAIL":
        return KNOWN_FAILURE
    return None


def _rank(change: dict) -> tuple:
    """Ordonne les changements par urgence, une transition sûre avant une suspecte."""
    return (CHANGE_ORDER.index(change["change"]), change["flaky"], change["test"])


def _counts(changes: list[dict]) -> dict[str, int]:
    """Compte les changements par nature, catégories vides comprises."""
    return {
        kind: sum(1 for change in changes if change["change"] == kind)
        for kind in CHANGE_ORDER
    }
