"""
Module d'exécution des commandes Robot Framework.

Gère l'exécution des tests avec :
- Gestion du stop signal scopé par session
- Notifications UI scopées par session
- Support multi-OS
- Exécutions parallèles via session_id

Chaque commande est une LISTE d'arguments (voir services/execution/commands.py),
exécutée sans shell. Règle SHELL_STR — docs/regles_apprises.md.
"""

import shlex
import signal
import subprocess
import sys
from pathlib import Path

import requests

from core.api_config import API_BASE_URL
from core.logging_config import get_logger
from core.paths import paths
from core.session_registry import registry

logger = get_logger(__name__)

# Code de sortie maison quand le run n'a pas pu démarrer (exécutable introuvable).
# 255 est dans la plage réservée de Robot Framework (252-255 = erreurs hors tests),
# donc jamais confondu avec « N tests ont échoué ».
EXIT_LAUNCH_FAILED = 255
SENSITIVE_VARIABLE_MARKERS = ("PASSWORD", "PASSWD", "SECRET", "TOKEN", "API_KEY", "APIKEY")
VARIABLE_OPTIONS = {"-v", "--variable"}

STOP_POLL_SECONDS = 0.5
# Delai laisse a Robot pour finir le test courant et ecrire ses rapports.
GRACEFUL_STOP_SECONDS = 20


def _mask_robot_variable(variable: str) -> str:
    """Masque la valeur d'une variable Robot Framework lorsque son nom est sensible.

    Args:
        variable: Variable au format ``NOM:valeur``.

    Returns:
        La variable originale si elle n'est pas sensible, sinon ``NOM:***``.
    """
    name, separator, _value = variable.partition(":")
    normalized_name = name.upper()
    if separator and any(marker in normalized_name for marker in SENSITIVE_VARIABLE_MARKERS):
        return f"{name}:***"
    return variable


def format_rf_command_for_log(command: list[str]) -> str:
    """Construit une représentation sûre d'une commande Robot pour les journaux.

    Seule la copie destinée à l'affichage est masquée. La liste originale, utilisée
    pour lancer le processus, n'est jamais modifiée.

    Args:
        command: Liste des arguments de la commande Robot Framework.

    Returns:
        La commande lisible avec les variables sensibles remplacées par ``***``.
    """
    masked_command: list[str] = []
    mask_next_variable = False
    for argument in command:
        if mask_next_variable:
            masked_command.append(_mask_robot_variable(argument))
            mask_next_variable = False
        elif argument in VARIABLE_OPTIONS:
            masked_command.append(argument)
            mask_next_variable = True
        elif argument.startswith("--variable="):
            option, variable = argument.split("=", 1)
            masked_command.append(f"{option}={_mask_robot_variable(variable)}")
        else:
            masked_command.append(argument)
    return shlex.join(masked_command)


def run_rf_command(command: list[str] | str, session_id: str | None = None) -> int:
    """
    Lance UNE commande Robot Framework et retourne son vrai code de sortie.

    `command` est une liste d'arguments (ex. ["robot", "-i", "smoke", ...]) passée
    à subprocess sans shell : aucun caractère du contenu (`&`, `|`, espaces...)
    n'est réinterprété, et les chemins avec espaces fonctionnent sans guillemets.

    Args:
        command: Liste d'arguments de la commande
        session_id: Identifiant de session (pour les logs)

    Returns:
        Code de sortie du process, ou EXIT_LAUNCH_FAILED s'il n'a pas pu démarrer
    """
    if isinstance(command, str):
        raise TypeError(
            "Les commandes RF doivent être des listes d'arguments, pas des chaînes shell. "
            "Voir la règle SHELL_STR dans docs/regles_apprises.md."
        )
    try:
        # Pas de shell= : la liste part directement à l'OS (règle SHELL_STR).
        # Groupe de processus dédié sous Windows : sans lui, on ne peut pas signaler
        # Robot sans signaler aussi le backend qui l'a lancé.
        creation_flags = (
            subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0
        )
        process = subprocess.Popen(command, creationflags=creation_flags)
    except FileNotFoundError:
        logger.error(
            "[%s] Exécutable introuvable : '%s'. L'environnement virtuel est-il activé ?",
            session_id,
            command[0],
        )
        logger.debug("Détail de l'échec de lancement", exc_info=True)
        return EXIT_LAUNCH_FAILED

    return _wait_or_stop(process, session_id)


def _interrupt(process, session_id: str | None) -> None:
    """Demande à Robot de s'arrêter en finissant proprement.

    Robot traite Ctrl-Break/SIGTERM comme un arrêt gracieux : il termine le test en
    cours puis écrit ses rapports. Le tuer d'emblée priverait du résultat partiel.
    """
    logger.info("[%s] Arrêt demandé : interruption de Robot Framework", session_id)
    try:
        if sys.platform == 'win32':
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            process.terminate()
    except OSError as exc:
        logger.warning("[%s] Interruption impossible : %s", session_id, exc)


def _wait_or_stop(process, session_id: str | None = None) -> int:
    """Attend la fin du process, en l'interrompant dès qu'un arrêt est demandé.

    Sans cette surveillance, le signal d'arrêt n'était lu qu'entre deux commandes :
    le bouton « Arrêter » n'arrêtait donc rien de ce qui tournait.
    """
    interrupted_for = None
    while True:
        try:
            return process.wait(timeout=STOP_POLL_SECONDS)
        except subprocess.TimeoutExpired:
            if interrupted_for is None:
                if _was_manually_stopped(session_id):
                    _interrupt(process, session_id)
                    interrupted_for = 0.0
                continue
            interrupted_for += STOP_POLL_SECONDS
            if interrupted_for >= GRACEFUL_STOP_SECONDS:
                logger.warning("[%s] Robot ne répond plus : arrêt forcé", session_id)
                process.kill()
                return process.wait()


def execute_rf_commands(
    rf_commands: list[list[str]],
    session_id: str | None = None,
    notify_complete: bool = True,
) -> int:
    """
    Exécute une liste de commandes Robot Framework.

    Args:
        rf_commands: Liste de commandes, chacune étant une liste d'arguments
        session_id: Identifiant de session (pour multi-exécution)
        notify_complete: Si True, notifie l'UI de la fin d'exécution

    Returns:
        Code de sortie de la dernière commande
    """
    # Nettoyer un éventuel stop_signal résiduel
    stop_path = _get_stop_signal_path(session_id)
    if stop_path.exists():
        logger.warning("[%s] stop_signal résiduel détecté, nettoyage", session_id)
        _cleanup_stop_signal(session_id)

    if session_id:
        registry.update(session_id, status='running')

    exit_code = 0
    for i, command in enumerate(rf_commands):
        logger.info(
            "[%s] Exécution de la commande RF (%s/%s) : %s",
            session_id,
            i + 1,
            len(rf_commands),
            format_rf_command_for_log(command),
        )
        exit_code = run_rf_command(command, session_id)
        log_completion = logger.info if exit_code == 0 else logger.warning
        log_completion("[%s] Commande terminée avec le code de sortie : %s", session_id, exit_code)

        if _was_manually_stopped(session_id):
            logger.info("[%s] Arrêt manuel détecté par le runner", session_id)
            if session_id:
                registry.update(session_id, status='stopped', exit_code=exit_code)
            if notify_complete:
                _notify_execution_complete(session_id)
            return exit_code

        if exit_code != 0:
            break

    if session_id:
        registry.update(session_id, exit_code=exit_code)

    if notify_complete:
        _notify_execution_complete(session_id)
    
    return exit_code


def _get_stop_signal_path(session_id: str | None = None) -> Path:
    """Retourne le chemin du signal d'arrêt, éventuellement propre à une session."""
    if session_id:
        return registry.stop_signal_path(session_id)
    return paths.STOP_SIGNAL


def _was_manually_stopped(session_id: str | None = None) -> bool:
    """Détecte si l'arrêt était manuel (fichier stop_signal présent)."""
    return _get_stop_signal_path(session_id).exists()


def was_manually_stopped(session_id: str | None = None) -> bool:
    """Indique si un arrêt a été demandé pour cette session.

    Exposé pour que l'orchestrateur ne enchaîne pas un rejeu sur un run interrompu.
    """
    return _was_manually_stopped(session_id)


def _cleanup_stop_signal(session_id: str | None = None) -> None:
    """Supprime le fichier de signal d'arrêt lorsqu'il existe."""
    try:
        stop_path = _get_stop_signal_path(session_id)
        if stop_path.exists():
            stop_path.unlink()
    except OSError as exc:
        logger.warning("[%s] Erreur lors de la suppression du stop_signal : %s", session_id, exc)
        logger.debug("Détail du nettoyage du stop_signal", exc_info=True)


def _notify_execution_complete(session_id: str | None = None) -> None:
    """Notifie l'API de la fin d'exécution sans faire échouer le run en cas d'indisponibilité."""
    try:
        requests.post(
            f'{API_BASE_URL}/execution-complete',
            json={'session_id': session_id},
            timeout=5
        )
    except requests.RequestException as exc:
        logger.warning("[%s] Notification de fin d'exécution échouée : %s", session_id, exc)
        logger.debug("Détail de la notification de fin d'exécution", exc_info=True)
