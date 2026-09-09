"""Validation partagée des payloads HTTP utilisés pour lancer des tests."""

from collections.abc import Iterable

ALLOWED_BROWSERS = frozenset({"chromium", "firefox", "webkit"})
VIEWPORT_DEVICES = {
    "1920x1080": "desktop",
    "768x1024": "tablet",
    "375x812": "mobile",
}
ALLOWED_RUN_WORKFLOWS = frozenset({"smoke"})


class RequestValidationError(ValueError):
    """Signale une valeur HTTP invalide qui doit produire une réponse 400."""


def require_json_object(data: object) -> dict:
    """Vérifie que le corps JSON est un objet.

    Args:
        data: Valeur décodée par Flask.

    Returns:
        Le dictionnaire reçu.

    Raises:
        RequestValidationError: Si le corps est absent ou n'est pas un objet.
    """
    if not isinstance(data, dict):
        raise RequestValidationError("Corps JSON invalide")
    return data


def validate_run_target(
    data: dict,
    default_browser: object,
    default_viewport: object,
) -> tuple[str, str, str]:
    """Valide le navigateur et le viewport d'une exécution web.

    Returns:
        Le triplet ``browser``, ``viewport`` et ``device`` normalisé.
    """
    browser = data.get("browser", default_browser)
    if not isinstance(browser, str) or browser not in ALLOWED_BROWSERS:
        raise RequestValidationError("Navigateur invalide")

    viewport = data.get("viewport", default_viewport)
    if not isinstance(viewport, str) or viewport not in VIEWPORT_DEVICES:
        raise RequestValidationError("Viewport invalide")
    return browser, viewport, VIEWPORT_DEVICES[viewport]


def validate_workflow(value: object) -> str:
    """Valide le workflow accepté par la route smoke générique."""
    if not isinstance(value, str) or value not in ALLOWED_RUN_WORKFLOWS:
        raise RequestValidationError("Workflow invalide")
    return value


def validate_string(value: object, field_name: str, allow_empty: bool = True) -> str:
    """Valide une chaîne HTTP sans conversion implicite.

    Args:
        value: Valeur reçue dans le payload.
        field_name: Nom public du champ utilisé dans le message d'erreur.
        allow_empty: Autorise ou non la chaîne vide.

    Returns:
        La chaîne reçue.
    """
    if not isinstance(value, str) or (not allow_empty and not value):
        raise RequestValidationError(f"{field_name} doit être une chaîne")
    return value


def _normalize_tag_list(
    raw_tags: object,
    field_name: str,
    catalog: dict[str, str],
) -> list[str]:
    """Valide une liste de tags et retourne les noms canoniques sans doublon."""
    if not isinstance(raw_tags, list):
        raise RequestValidationError(f"{field_name} doit être une liste")

    normalized: list[str] = []
    seen: set[str] = set()
    for raw_tag in raw_tags:
        if not isinstance(raw_tag, str) or not raw_tag.strip():
            raise RequestValidationError(f"{field_name} contient un tag invalide")
        lookup_key = raw_tag.strip().casefold()
        if lookup_key not in catalog:
            raise RequestValidationError(f"Tag inconnu : {raw_tag.strip()}")
        if lookup_key not in seen:
            seen.add(lookup_key)
            normalized.append(catalog[lookup_key])
    return normalized


def normalize_tag_filters(
    raw_include_tags: object,
    raw_exclude_tags: object,
    available_tags: Iterable[str],
) -> tuple[list[str], list[str]]:
    """Valide les filtres contre le catalogue réel de Robot Framework.

    La comparaison est insensible à la casse. Aucun nombre maximal arbitraire
    n'est appliqué : le catalogue réel borne naturellement les valeurs acceptées.

    Args:
        raw_include_tags: Liste reçue dans ``include_tags``.
        raw_exclude_tags: Liste reçue dans ``exclude_tags``.
        available_tags: Tags réellement découverts dans les suites Robot.

    Returns:
        Les listes canoniques d'inclusion et d'exclusion, sans doublons.

    Raises:
        RequestValidationError: Si un type, un tag ou un conflit est invalide.
    """
    catalog = {tag.casefold(): tag for tag in available_tags}
    include_tags = _normalize_tag_list(raw_include_tags, "include_tags", catalog)
    exclude_tags = _normalize_tag_list(raw_exclude_tags, "exclude_tags", catalog)

    conflicts = {tag.casefold() for tag in include_tags} & {
        tag.casefold() for tag in exclude_tags
    }
    if conflicts:
        conflicting_tag = catalog[sorted(conflicts)[0]]
        raise RequestValidationError(
            f"Le tag {conflicting_tag} ne peut pas être inclus et exclu"
        )
    return include_tags, exclude_tags


def validate_boolean(value: object, field_name: str) -> bool:
    """Refuse les pseudo-booléens tels que ``1`` ou ``"true"``."""
    if type(value) is not bool:
        raise RequestValidationError(f"{field_name} doit être un booléen")
    return value


def validate_selection_count(value: object, is_random: bool) -> int:
    """Valide le nombre de tests aléatoires sans modifier silencieusement sa valeur."""
    if type(value) is not int or value < 0:
        raise RequestValidationError("nb_selection doit être un entier positif ou nul")
    if not is_random and value != 0:
        raise RequestValidationError("nb_selection est réservé à l'exécution aléatoire")
    return value