"""Diagnostic d'un locator qui ne résout plus, au moment exact où le test échoue.

Ce listener ne répare rien. Un locator « auto-réparé » rendrait le test vert alors
que l'ancrage a cassé - et masquerait une régression produit le jour où l'élément
a disparu pour une bonne raison. Il échoue donc comme avant, mais le log porte la
réponse : ce qui était attendu, ce que la page contient, et quels éléments s'en
rapprochent.

Usage :
    robot --listener robot_listeners.locator_diagnostic.LocatorDiagnostic Tests/
"""

from __future__ import annotations

from difflib import SequenceMatcher

from robot.libraries.BuiltIn import BuiltIn

from core.logging_config import get_logger

logger = get_logger(__name__)

# Keywords Browser dont le premier argument positionnel désigne un élément. Les
# autres (New Page, Go To) prennent une URL : les sonder n'aurait aucun sens.
KEYWORDS_A_LOCATOR = frozenset({
    "Check Checkbox", "Clear Text", "Click", "Fill Secret", "Fill Text", "Focus",
    "Get Attribute", "Get Element Count", "Get Element States", "Get Property",
    "Get Text", "Hover", "Press Keys", "Select Options By", "Tap", "Type Text",
    "Uncheck Checkbox", "Wait For Elements State",
})

MAX_CANDIDATS = 5
# Au-delà, on décrit une page entière plutôt qu'on ne cherche un élément.
MAX_ELEMENTS_INSPECTES = 400

_JS_INVENTAIRE = """
() => Array.from(document.querySelectorAll(
    'a, button, input, select, textarea, [role], [data-test], [data-testid]'
)).filter(e => e.children.length === 0
            || ['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'].includes(e.tagName)
).slice(0, %d).map(e => ({
    tag: e.tagName.toLowerCase(),
    id: e.id || '',
    testid: e.getAttribute('data-test') || e.getAttribute('data-testid') || '',
    nom: (e.getAttribute('aria-label') || e.getAttribute('placeholder')
          || e.value || e.textContent || '').trim().slice(0, 60),
}))
""" % MAX_ELEMENTS_INSPECTES


def _mots(texte: str) -> str:
    """Réduit un sélecteur ou un libellé à ses mots, pour les rendre comparables."""
    return "".join(c if c.isalnum() else " " for c in texte.lower()).strip()


def _score(attendu: str, candidat: dict) -> float:
    """Proximité du candidat avec ce qui était cherché, sur son meilleur attribut."""
    cible = _mots(attendu)
    valeurs = [candidat.get(champ, "") for champ in ("id", "testid", "nom")]
    return max(
        (SequenceMatcher(None, cible, _mots(v)).ratio() for v in valeurs if v),
        default=0.0,
    )


def locator_attendu(keyword: str, args: list[str]) -> str | None:
    """Le locator visé, ou None si ce keyword ne vise pas d'élément."""
    if keyword not in KEYWORDS_A_LOCATOR or not args:
        return None
    premier = args[0]
    return premier[len("selector="):] if premier.startswith("selector=") else premier


def classer(attendu: str, candidats: list[dict], limite: int = MAX_CANDIDATS) -> list[tuple]:
    """Les candidats les plus proches en premier."""
    notes = [(_score(attendu, c), c) for c in candidats]
    return sorted(notes, key=lambda note: note[0], reverse=True)[:limite]


def _decrire(candidat: dict) -> str:
    reperes = [f"#{candidat['id']}" if candidat.get("id") else "",
               f"data-test={candidat['testid']}" if candidat.get("testid") else ""]
    return " ".join([candidat.get("tag", "")] + [r for r in reperes if r]
                    + [f"« {candidat['nom']} »" if candidat.get("nom") else ""])


def rapport(keyword: str, attendu: str, resolu: str, compte: int | None,
            classes: list[tuple]) -> str:
    """Le texte déposé dans le log Robot, à côté de l'échec."""
    lignes = [f"Diagnostic de locator - {keyword}", f"  Attendu : {attendu}"]
    if resolu != attendu:
        lignes.append(f"  Résolu  : {resolu}")
    if compte == 0:
        lignes.append("  0 élément sur la page : l'ancrage ne désigne plus rien.")
    elif compte is not None and compte > 1:
        lignes.append(f"  {compte} éléments correspondent : l'ancrage n'est plus unique.")
    if classes:
        lignes.append("  Éléments les plus proches trouvés sur la page :")
        lignes += [f"    {note:.2f}  {_decrire(c)}" for note, c in classes]
    lignes.append("  Aucune réparation n'est tentée : le test reste en échec.")
    return "\n".join(lignes)


class LocatorDiagnostic:
    """Sonde la page vivante au premier échec d'un keyword Browser de chaque test."""

    ROBOT_LISTENER_API_VERSION = 2

    def __init__(self):
        self.sonde_faite = False

    def start_test(self, name, attrs):
        self.sonde_faite = False

    def end_keyword(self, name, attrs):
        # Un échec remonte toute la pile d'appels : seul le keyword le plus profond,
        # vu en premier, désigne le locator réellement en cause.
        if self.sonde_faite or attrs.get("status") != "FAIL":
            return
        if attrs.get("libname") != "Browser":
            return
        attendu = locator_attendu(attrs.get("kwname") or "", attrs.get("args") or [])
        if attendu is None:
            return
        self.sonde_faite = True
        try:
            self._sonder(name, attendu)
        except Exception as exc:  # une sonde ne doit jamais masquer l'échec qu'elle observe
            logger.debug("Diagnostic de locator impossible : %s", exc)

    def _sonder(self, keyword: str, attendu: str) -> None:
        builtin = BuiltIn()
        browser = builtin.get_library_instance("Browser")
        resolu = builtin.replace_variables(attendu)

        compte = None
        try:
            compte = browser.get_element_count(resolu)
        except Exception:  # sélecteur invalide : le compte n'apprend rien, les candidats si
            pass

        # Un ancrage qui désigne exactement un élément n'est pas la cause de l'échec.
        # Diagnostiquer quand même noierait la vraie erreur sous une liste de candidats.
        if compte == 1:
            return

        candidats = browser.evaluate_javascript(None, _JS_INVENTAIRE.strip()) or []
        builtin.log(rapport(keyword, attendu, resolu, compte, classer(resolu, candidats)),
                    "WARN")
