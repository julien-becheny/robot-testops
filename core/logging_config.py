"""Configuration commune des journaux produits par TestOps."""

import logging
import sys

LOGGER_NAME = "testops"
HANDLER_NAME = "testops-console"
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def _resolve_level(level: str | int) -> int:
    """Convertit un niveau textuel ou numérique en niveau reconnu par Python.

    Args:
        level: Niveau demandé, par exemple ``"DEBUG"``, ``"INFO"`` ou
            ``logging.WARNING``.

    Returns:
        Le niveau numérique correspondant. Une valeur inconnue utilise ``INFO``.
    """
    if isinstance(level, int):
        return level
    resolved = getattr(logging, str(level).upper(), logging.INFO)
    return resolved if isinstance(resolved, int) else logging.INFO


def configure_logging(level: str | int = logging.INFO) -> logging.Logger:
    """Configure le logger principal de TestOps pour une sortie dans la console.

    La configuration est idempotente : plusieurs appels réutilisent le même
    gestionnaire de sortie afin de ne pas afficher chaque message plusieurs fois.

    Args:
        level: Niveau minimal à afficher, sous forme textuelle ou numérique.

    Returns:
        Le logger principal ``testops`` configuré.
    """
    logger = logging.getLogger(LOGGER_NAME)
    resolved_level = _resolve_level(level)
    logger.setLevel(resolved_level)
    logger.propagate = False

    handler = next(
        (current for current in logger.handlers if current.get_name() == HANDLER_NAME),
        None,
    )
    if handler is None:
        handler = logging.StreamHandler(sys.stdout)
        handler.set_name(HANDLER_NAME)
        handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(handler)
    handler.setLevel(resolved_level)
    return logger


def get_logger(module_name: str) -> logging.Logger:
    """Retourne un logger enfant identifié par le module qui écrit le message.

    Args:
        module_name: Nom Python du module appelant, généralement ``__name__``.

    Returns:
        Un logger nommé ``testops.<module>`` qui hérite de la configuration
        centrale.
    """
    suffix = module_name.removeprefix(f"{LOGGER_NAME}.")
    return logging.getLogger(f"{LOGGER_NAME}.{suffix}")