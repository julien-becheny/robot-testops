"""Nommage des traces Playwright : un fichier par test, identifiable sans le rapport.

Laissee a elle-meme, Browser library ecrit `trace_context=<uuid>.zip` : le fichier
existe, mais rien ne dit quel test il raconte. On lui impose donc un nom derive du
nom du test.
"""

import re
import unicodedata

from robot.libraries.BuiltIn import BuiltIn
from robot.utils import is_truthy

TRACE_DIR = "browser/traces"
_MAX_NAME_LENGTH = 80

# Un run = un process robot. Deux tests homonymes (suites differentes) viseraient le
# meme fichier, et le second effacerait la trace du premier sans rien dire.
_used_names: set[str] = set()


def _slug(name: str) -> str:
    """Reduit un nom de test a ce qu'un systeme de fichiers accepte partout."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Za-z0-9]+", "_", ascii_name).strip("_").lower()
    return slug[:_MAX_NAME_LENGTH] or "test"


def _unique(name: str) -> str:
    """Suffixe le nom tant qu'un autre contexte du meme run l'a deja pris."""
    candidate = name
    suffix = 2
    while candidate in _used_names:
        candidate = f"{name}_{suffix}"
        suffix += 1
    _used_names.add(candidate)
    return candidate


def get_trace_target() -> str | None:
    """Retourne le fichier de trace du test courant, ou None si la trace est inactive.

    A passer a `New Context  tracing=` : le chemin est relatif au dossier de rapport
    du run. Ne jamais activer la trace par la variable ${ROBOT_FRAMEWORK_BROWSER_TRACING}
    de la librairie : elle court-circuite ce nom et reimpose l'identifiant de contexte.
    """
    builtin = BuiltIn()
    if not is_truthy(builtin.get_variable_value("${TRACING}", False)):
        return None
    test_name = builtin.get_variable_value("${TEST NAME}") or "suite"
    return f"{TRACE_DIR}/{_unique(_slug(test_name))}.zip"
