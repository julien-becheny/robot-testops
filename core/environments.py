"""Référentiel des environnements : quelle installation cible, quelle URL par module.

Deux dimensions sont volontairement séparées :

- l'ENVIRONNEMENT (recette, préprod…) est choisi au lancement - il fixe le host ;
- le MODULE (patrimoine, travaux…) est déclaré par le test lui-même - il fixe le chemin.

Aucune URL n'est donc écrite en dur dans un test : elle est résolue à l'exécution par
:func:`resolve_module_url`. Un run filtré par tags peut traverser plusieurs modules,
chacun tapant sa propre URL, sans rien changer au lancement.

Les mots de passe ne sont jamais stockés dans ``config/environments.yaml``, qui est
versionné : celui-ci ne porte que la *référence* du secret, résolu depuis
``variables_config.json`` (ignoré par git) sous la clé ``RF_SECRET_<ref>``.
"""

# Standard library
from typing import Any

# Third-party
import yaml

# Local/projet
from core import config
from core.paths import paths

ENVIRONMENTS_FILE = paths.CONFIG / "environments.yaml"
SECRET_PREFIX = "RF_SECRET_"  # pragma: allowlist secret

# Niveau de l'installation. Il ne change rien a l'execution : il sert a ce que
# personne ne lance un run sur la production en croyant taper une recette.
TIERS = ("demo", "recette", "preprod", "prod")
DEFAULT_TIER = "demo"

_ABSOLUTE_SCHEMES = ("http://", "https://")


def _load_all() -> dict[str, Any]:
    """Lit le référentiel YAML brut.

    Raises:
        ValueError: fichier illisible, YAML mal formé, ou racine qui n'est pas
            un dictionnaire d'environnements.
    """
    try:
        raw = yaml.safe_load(ENVIRONMENTS_FILE.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(
            f"Référentiel des environnements illisible ({ENVIRONMENTS_FILE}) : {exc}"
        ) from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"Référentiel des environnements mal formé : {exc}") from exc

    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(
            "Le référentiel des environnements doit être un dictionnaire "
            "{identifiant: définition}."
        )
    return raw


def _validate(env_id: str, entry: Any) -> dict[str, Any]:
    """Contrôle la définition d'un environnement saisie à la main.

    Raises:
        ValueError: définition incomplète, mal typée, ou contenant un mot de passe.
    """
    if not isinstance(entry, dict):
        raise ValueError(f"L'environnement '{env_id}' doit être un dictionnaire.")

    base = entry.get("base")
    if not isinstance(base, str) or not base.startswith(_ABSOLUTE_SCHEMES):
        raise ValueError(
            f"L'environnement '{env_id}' doit définir une 'base' commençant par "
            "http:// ou https://."
        )

    modules = entry.get("modules") or {}
    if not isinstance(modules, dict):
        raise ValueError(f"'modules' de l'environnement '{env_id}' doit être un dictionnaire.")
    for module_id, path in modules.items():
        if not isinstance(path, str) or not path:
            raise ValueError(
                f"Le chemin du module '{module_id}' ({env_id}) doit être une chaîne non vide."
            )

    accounts = entry.get("accounts") or {}
    if not isinstance(accounts, dict):
        raise ValueError(f"'accounts' de l'environnement '{env_id}' doit être un dictionnaire.")
    for profile, account in accounts.items():
        if not isinstance(account, dict):
            raise ValueError(f"Le compte '{profile}' ({env_id}) doit être un dictionnaire.")
        # environments.yaml est versionné : un mot de passe en clair y serait publié.
        if "password" in account:
            raise ValueError(
                f"Le compte '{profile}' ({env_id}) contient un mot de passe en clair. "
                f"Utilisez 'password_ref' et stockez la valeur dans {SECRET_PREFIX}<ref>."
            )
        if not isinstance(account.get("username"), str):
            raise ValueError(f"Le compte '{profile}' ({env_id}) doit définir un 'username'.")

    tier = entry.get("tier") or DEFAULT_TIER
    if tier not in TIERS:
        raise ValueError(
            f"Le 'tier' de l'environnement '{env_id}' doit valoir l'un de : "
            f"{', '.join(TIERS)}."
        )

    return {"label": entry.get("label") or env_id, "base": base, "tier": tier,
            "modules": modules, "accounts": accounts}


def get_environment(env_id: str) -> dict[str, Any] | None:
    """Retourne la définition validée d'un environnement, ou None s'il est inconnu.

    Le retour None fait office de liste blanche : toute valeur non déclarée dans
    le référentiel est refusée par les routes qui l'utilisent.
    """
    entry = _load_all().get(env_id)
    if entry is None:
        return None
    return _validate(env_id, entry)


def list_environments() -> list[dict[str, Any]]:
    """Retourne les environnements déclarés, pour peupler l'interface."""
    return [
        {
            "id": env_id,
            "label": validated["label"],
            "base": validated["base"],
            "tier": validated["tier"],
            "modules": sorted(validated["modules"]),
        }
        for env_id, validated in (
            (env_id, _validate(env_id, entry)) for env_id, entry in _load_all().items()
        )
    ]


def active_environment() -> str | None:
    """Retourne l'environnement sélectionné, ou le premier déclaré à défaut."""
    selected = config.get("RF_ENVIRONMENT")
    if selected and get_environment(selected):
        return selected
    declared = list(_load_all())
    return declared[0] if declared else None


def resolve_module_url(env_id: str, module: str) -> str:
    """Compose l'URL d'un module dans un environnement donné.

    Un chemin absolu (http/https) déclaré pour le module remplace la base : c'est
    le cas d'un module hébergé sur son propre host (brique tierce).

    Raises:
        ValueError: environnement ou module non déclaré. L'absence de repli
            silencieux évite de tester une page arbitraire sans s'en apercevoir.
    """
    environment = get_environment(env_id)
    if environment is None:
        raise ValueError(
            f"Environnement '{env_id}' inconnu. Déclarés : {', '.join(_load_all()) or 'aucun'}."
        )

    path = environment["modules"].get(module)
    if path is None:
        known = ", ".join(sorted(environment["modules"])) or "aucun"
        raise ValueError(
            f"Module '{module}' non déclaré dans l'environnement '{env_id}'. Connus : {known}."
        )

    if path.startswith(_ABSOLUTE_SCHEMES):
        return path
    return f"{environment['base'].rstrip('/')}/{path.lstrip('/')}"


def resolve_account(env_id: str, profile: str) -> dict[str, str]:
    """Retourne le couple identifiant/mot de passe d'un profil pour un environnement.

    Le mot de passe provient de ``variables_config.json`` (non versionné) via la
    clé ``RF_SECRET_<password_ref>``.

    Raises:
        ValueError: environnement, profil ou secret manquant. Le message ne
            contient jamais la valeur du secret.
    """
    environment = get_environment(env_id)
    if environment is None:
        raise ValueError(f"Environnement '{env_id}' inconnu.")

    account = environment["accounts"].get(profile)
    if account is None:
        known = ", ".join(sorted(environment["accounts"])) or "aucun"
        raise ValueError(
            f"Profil '{profile}' non déclaré dans l'environnement '{env_id}'. Connus : {known}."
        )

    password_ref = account.get("password_ref")
    if not password_ref:
        raise ValueError(f"Le compte '{profile}' ({env_id}) doit définir un 'password_ref'.")

    secret_key = f"{SECRET_PREFIX}{password_ref}"
    password = config.get(secret_key)
    if not password:
        raise ValueError(
            f"Mot de passe absent pour le profil '{profile}' ({env_id}) : renseignez "
            f"'{secret_key}' dans config/variables_config.json (jamais dans "
            "config/environments.yaml, qui est versionné)."
        )

    return {"username": account["username"], "password": password}
