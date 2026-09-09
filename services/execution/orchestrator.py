"""
Orchestration des workflows d'exécution de tests.

Chaque workflow est une séquence de commandes RF.
Pour ajouter un workflow, créer une fonction dans commands.py
et l'intégrer ici.
"""

import datetime
import random

from core.logging_config import get_logger
from core.paths import paths
from services.execution import run_meta
from services.execution.commands import (
    get_randomized_cmd,
    get_smoke_cmd,
    get_tag_filtered_cmd,
)
from services.execution.rerun import rerun_failed_tests
from services.execution.runner import (
    _notify_execution_complete,
    execute_rf_commands,
    was_manually_stopped,
)
from services.tags.manager import get_matching_tests

logger = get_logger(__name__)


def run_workflow(workflow: str, include_tags: list = None, exclude_tags: list = None,
                 rerun_failed: bool = False, is_random: bool = False,
                 nb_selection: int = 0, session_id: str = None, browser: str = None,
                 device: str = None):
    """
    Lance un workflow d'exécution.
    
    Args:
        workflow: Nom du workflow ('smoke', 'tag_filtered', 'randomized')
        include_tags: Tags à inclure (pour tag_filtered / randomized)
        exclude_tags: Tags à exclure (pour tag_filtered / randomized)
        rerun_failed: Si True, relance les tests échoués après l'exécution
        is_random: Si True, sélectionne un sous-ensemble aléatoire de tests
        nb_selection: Nombre de tests à sélectionner (mode aléatoire)
        session_id: Identifiant de session pour multi-exécution
        browser: Navigateur à utiliser, Chromium par défaut
        device: Profil d'appareil à utiliser, desktop par défaut

    Returns:
        Aucun résultat. Le suivi d'exécution est publié via la session.
    """
    base_stamp = datetime.datetime.now().strftime("%Y_%m_%d-%H%M%S")
    browser_label = browser or 'chromium'
    device_label = device or 'desktop'
    dt_stamp = (
        f"{base_stamp}_{browser_label}_{device_label}_{session_id}"
        if session_id
        else base_stamp
    )
    
    if session_id:
        from core.session_registry import registry
        registry.update(session_id, dt_stamp=dt_stamp)

    run_meta.write(dt_stamp, workflow=workflow, engine='playwright',
                   browser=browser_label, device=device_label)

    include_tags = include_tags or []
    exclude_tags = exclude_tags or []
    
    sid = session_id or 'default'
    logger.info("[%s] Workflow : %s | Timestamp : %s", sid, workflow, dt_stamp)
    if is_random:
        logger.info("[%s] Exécution aléatoire (%s tests)", sid, nb_selection)
    if rerun_failed:
        logger.info("[%s] Rerun des échecs activé", sid)
    
    if workflow == 'smoke':
        commands = [get_smoke_cmd(dt_stamp, session_id=session_id, browser=browser_label,
                                    device=device_label)]
    
    elif workflow == 'tag_filtered':
        commands = [get_tag_filtered_cmd(dt_stamp, include_tags, exclude_tags,
                                         rerun_failed, session_id=session_id, browser=browser_label,
                                         device=device_label)]
    
    elif workflow == 'randomized':
        matching = get_matching_tests(include_tags, exclude_tags)
        test_names = [t['name'] for t in matching]
        count = min(nb_selection, len(test_names)) if nb_selection > 0 else len(test_names)
        selected = random.sample(test_names, count)
        logger.info("[%s] %s test(s) sélectionné(s) parmi %s", sid, count, len(test_names))
        for test_name in selected:
            logger.info("[%s] Test sélectionné : %s", sid, test_name)
        commands = [get_randomized_cmd(dt_stamp, selected, rerun_failed,
                                        session_id=session_id, browser=browser_label,
                                        device=device_label)]
    
    else:
        logger.error("[%s] Workflow inconnu : %s", sid, workflow)
        return
    
    exit_code = execute_rf_commands(commands, session_id=session_id,
                                    notify_complete=not rerun_failed)
    
    if rerun_failed:
        # Un run interrompu n'a pas d'echecs a rejouer : il a des tests non joues.
        if exit_code != 0 and not was_manually_stopped(session_id):
            report_folder = str(paths.get_report_folder(dt_stamp))
            logger.info("[%s] Re-run des tests échoués", sid)
            rerun_failed_tests(report_folder, dt_stamp, session_id=session_id,
                               browser=browser_label, device=device_label)
        _notify_execution_complete(session_id)
    
    if session_id:
        from core.session_registry import registry
        registry.update(session_id, status='completed')
    
    log_completion = logger.info if exit_code == 0 else logger.warning
    log_completion("[%s] Workflow terminé (code de sortie : %s)", sid, exit_code)
