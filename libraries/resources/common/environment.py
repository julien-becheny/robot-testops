"""Résolution de l'environnement côté Robot Framework.

Expose deux keywords : `Get Module Url` et `Get Account`. Le test nomme son module
et son profil de compte ; l'URL et les identifiants sont résolus à l'exécution
depuis ``config/environments.yaml`` (cf. ``core.environments``).

Le mot de passe est encapsulé dans un ``Secret`` : ni l'assignation de variable ni
les arguments des keywords suivants ne l'écrivent dans le log Robot.

Importé côté Robot via ::

    Library  ${CURDIR}/environment.py
"""

# Standard library
import sys
from pathlib import Path

# Bootstrap : garantir que la racine projet est sur le sys.path pour importer core
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Third-party
from robot.api.types import Secret

# Local/projet
from core import environments


def _target(environment: str | None) -> str:
    """Retourne l'environnement demandé, ou celui configuré si l'argument est vide.

    Le repli permet de lancer `robot` en direct sans passer `-v ENVIRONMENT`.
    """
    return environment or environments.active_environment() or ""


def get_module_url(module: str, environment: str | None = None) -> str:
    """Compose l'URL d'un module dans l'environnement courant.

    Échoue explicitement si le module n'est pas déclaré : sans cela, un test
    pourrait viser une page arbitraire et passer pour de mauvaises raisons.
    """
    return environments.resolve_module_url(_target(environment), module)


def get_account(profile: str = "STANDARD", environment: str | None = None) -> dict:
    """Retourne ``{username, password}`` pour un profil dans l'environnement courant.

    Le mot de passe est un ``Secret`` : passez-le à `Fill Secret`, jamais à `Fill Text`.
    """
    account = environments.resolve_account(_target(environment), profile)
    return {"username": account["username"], "password": Secret(account["password"])}
