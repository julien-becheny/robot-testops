"""
Génération des commandes Robot Framework.

Architecture extensible : chaque workflow a sa fonction get_*_cmd().
Pour ajouter un nouveau workflow, créer une nouvelle fonction ici.

CONTRAT : ces fonctions retournent une LISTE D'ARGUMENTS (`list[str]`), jamais une
chaîne shell. La liste part telle quelle dans `subprocess.run()` sans `shell=True`,
donc aucun shell n'interprète le contenu : un tag ou un nom de test contenant `&`,
`|`, `;`, un espace ou des guillemets reste une donnée. Voir la règle SHELL_STR dans
docs/regles_apprises.md.
"""

import sys

from core import config, environments
from core.paths import paths

# Le smoke ne se filtre pas par tags : il joue cette suite, et elle seule.
SMOKE_SUITE = paths.TEST_SUITES / 'web' / 'saucedemo' / '00_smoke.robot'


def robot_command() -> list[str]:
    """Amorce d'une commande Robot, liee a l'interpreteur qui execute TestOps.

    Appeler `robot` tout court laisserait le PATH decider : sur un poste ou un autre
    projet a ete active, les tests tourneraient avec SES librairies (autre version de
    Browser, autre Robot) et echoueraient pour des raisons imaginaires.
    """
    return [sys.executable, "-m", "robot"]


def _listener_arg(session_id=None, phase: str = 'run') -> list[str]:
    """Construit les arguments --listener : avancement du run, puis diagnostic.

    La phase (`run` ou `rerun`) distingue le premier passage du rejeu : les deux
    envoient leur propre avancement, sur la meme session.

    Le diagnostic de locator ne coute rien tant qu'aucun keyword Browser n'echoue :
    il n'ouvre rien, il interroge la page deja ouverte.
    """
    listener = "robot_listeners.execution_listener.ExecutionListener"
    suffixe = f"{session_id}:{phase}" if session_id else f":{phase}"
    return ["--listener", f"{listener}:{suffixe}",
            "--listener", "robot_listeners.locator_diagnostic.LocatorDiagnostic"]


def _default_exclusions() -> list[str]:
    """Tags jamais joues par les runs habituels.

    `appium` designe les suites qui exigent un appareil connecte (test_suites/appium/) :
    sans lui, elles echoueraient sans rien apprendre. Elles se lancent par get_appium_cmd.
    `quarantaine` met de cote un test juge instable : il sort du verdict sans disparaitre
    du depot, et la page de sante de la suite le rappelle a l'ordre.
    """
    excluded = ("not_ready", "in_dev", "blocked", "deprecated", "appium", "quarantaine")
    return [arg for tag in excluded for arg in ("-e", tag)]


def _slow_mo_arg() -> list[str]:
    """Injecte -v SLOW_MO (ralenti Playwright, reglage global RF_SLOW_MO). Defaut off."""
    value = config.get('RF_SLOW_MO', '0:00:00') or '0:00:00'
    return ["-v", f"SLOW_MO:{value}"]


def _tracing_arg() -> list[str]:
    """Active la trace Playwright quand le reglage global RF_TRACING le demande.

    La variable transmise est celle du depot (`${TRACING}`), pas celle de Browser
    library : `${ROBOT_FRAMEWORK_BROWSER_TRACING}` court-circuite le nom de fichier
    choisi par le test et reimpose `trace_context=<uuid>.zip`, illisible. Le keyword
    `Open Test Browser` lit `${TRACING}` et nomme la trace d'apres le test.
    Reglage off : rien n'est injecte, le run est strictement celui d'avant.
    """
    value = str(config.get('RF_TRACING', '') or '').strip().lower()
    if value not in ("1", "true", "on", "yes"):
        return []
    return ["-v", "TRACING:True"]


def _environment_arg() -> list[str]:
    """Injecte -v ENVIRONMENT : l'installation cible du run.

    Seul l'identifiant transite. Le module est declare par chaque test, et l'URL
    est composee a l'execution (cf. core.environments) : un run filtre par tags
    peut donc traverser plusieurs modules, chacun sur sa propre URL.
    """
    return ["-v", f"ENVIRONMENT:{environments.active_environment() or ''}"]


def _actions_arg(engine: str = 'playwright') -> list[str]:
    """Injecte -v ACTIONS : l'adaptateur qui traduit les primitives multi-moteur.

    Les suites de test_suites/multi_moteur/ sont ecrites une seule fois, dans un
    vocabulaire neutre, et s'executent avec Playwright ou Appium selon l'adaptateur
    designe ici. Les autres suites ignorent cette variable : elles appellent leur
    librairie directement.
    """
    engine = 'appium' if str(engine).lower() == 'appium' else 'playwright'
    actions = (paths.RESOURCES / 'common' / f'actions_{engine}.resource').as_posix()
    return ["-v", f"ACTIONS:{actions}"]


def get_smoke_cmd(dt_stamp: str, session_id: str = None, browser: str = 'chromium',
                  device: str = 'desktop') -> list[str]:
    """
    Commande pour exécuter le test smoke.

    Args:
        dt_stamp: Timestamp de l'exécution
        session_id: Identifiant de session
        browser: Navigateur cible
        device: Label de l'appareil

    Returns:
        Liste d'arguments Robot Framework
    """
    report_dir = paths.REPORTS / dt_stamp

    cmd = robot_command()
    cmd += _listener_arg(session_id)
    cmd += ["-d", str(report_dir)]
    cmd += ["-o", "output.xml", "-r", "report.html", "-l", "log.html"]
    cmd += ["-v", f"BROWSER:{browser}"]
    cmd += ["-v", f"DEVICE:{device}"]
    cmd += _slow_mo_arg()
    cmd += _tracing_arg()
    cmd += _environment_arg()
    browser_title = browser.capitalize()
    device_title = device.capitalize()
    cmd += ["-N", f"Smoke_Test_{browser_title}_{device_title}"]
    cmd += [str(SMOKE_SUITE)]

    return cmd


def get_tag_filtered_cmd(dt_stamp: str, include_tags: list, exclude_tags: list,
                         rerun_failed: bool = False, session_id: str = None,
                         browser: str = 'chromium', device: str = 'desktop') -> list[str]:
    """
    Commande pour exécuter des tests filtrés par tags.

    Args:
        dt_stamp: Timestamp de l'exécution
        include_tags: Tags à inclure
        exclude_tags: Tags à exclure
        rerun_failed: Si True, écrit dans Output_original/ pour permettre le merge
        browser: Navigateur cible
        device: Label de l'appareil

    Returns:
        Liste d'arguments Robot Framework
    """
    if rerun_failed:
        report_dir = paths.REPORTS / dt_stamp / "Output_original"
        xml_name = "output_original.xml"
        report_name = "report_original.html"
        log_name = "log_original.html"
    else:
        report_dir = paths.REPORTS / dt_stamp
        xml_name = "output.xml"
        report_name = "report.html"
        log_name = "log.html"

    cmd = robot_command()
    cmd += _listener_arg(session_id)

    for tag in include_tags:
        cmd += ["-i", tag]

    cmd += _default_exclusions()

    for tag in exclude_tags:
        cmd += ["-e", tag]

    cmd += ["-d", str(report_dir)]
    cmd += ["-o", xml_name, "-r", report_name, "-l", log_name]
    cmd += ["-v", f"BROWSER:{browser}"]
    cmd += ["-v", f"DEVICE:{device}"]
    cmd += _slow_mo_arg()
    cmd += _tracing_arg()
    cmd += _environment_arg()
    cmd += _actions_arg()
    browser_title = browser.capitalize()
    device_title = device.capitalize()
    cmd += ["-N", f"Execution_Filtree_{browser_title}_{device_title}"]
    cmd += [str(paths.TEST_SUITES)]

    return cmd


def get_randomized_cmd(dt_stamp: str, selected_tests: list,
                       rerun_failed: bool = False, session_id: str = None,
                       browser: str = 'chromium', device: str = 'desktop') -> list[str]:
    """
    Commande pour exécuter un échantillon aléatoire de tests.

    Les tests sont sélectionnés en amont (orchestrator) puis passés
    via un fichier d'arguments (--argumentfile). L'ordre d'exécution
    est randomisé via --randomize all.

    Args:
        dt_stamp: Timestamp de l'exécution
        selected_tests: Liste des noms de tests sélectionnés
        rerun_failed: Si True, écrit dans Output_original/ pour permettre le merge
        browser: Navigateur cible
        device: Label de l'appareil

    Returns:
        Liste d'arguments Robot Framework
    """
    run_dir = paths.REPORTS / dt_stamp
    run_dir.mkdir(parents=True, exist_ok=True)

    # La sélection reste attachée à son rapport et ne peut pas être écrasée par
    # une autre session lancée au même instant.
    args_file = run_dir / "selected_tests.args"
    with args_file.open('w', encoding='utf-8') as args_stream:
        for test in selected_tests:
            args_stream.write(f'--test {test}\n')

    if rerun_failed:
        report_dir = run_dir / "Output_original"
        xml_name = "output_original.xml"
        report_name = "report_original.html"
        log_name = "log_original.html"
    else:
        report_dir = run_dir
        xml_name = "output.xml"
        report_name = "report.html"
        log_name = "log.html"

    cmd = robot_command()
    cmd += ["--randomize", "all"]
    cmd += _listener_arg(session_id)
    cmd += ["--argumentfile", str(args_file)]
    cmd += _default_exclusions()
    cmd += ["-d", str(report_dir)]
    cmd += ["-o", xml_name, "-r", report_name, "-l", log_name]
    cmd += ["-v", f"BROWSER:{browser}"]
    cmd += ["-v", f"DEVICE:{device}"]
    cmd += _slow_mo_arg()
    cmd += _tracing_arg()
    cmd += _environment_arg()
    cmd += _actions_arg()
    browser_title = browser.capitalize()
    device_title = device.capitalize()
    cmd += ["-N", f"Execution_Randomisee_{browser_title}_{device_title}"]
    cmd += [str(paths.TEST_SUITES)]

    return cmd


def get_campaign_cmd(dt_stamp: str, tests: list, rerun_failed: bool = False,
                     session_id: str = None, browser: str = 'chromium',
                     device: str = 'desktop') -> list[str]:
    """
    Commande RF pour un LOT de campagne : liste de tests explicite sur UNE cible
    (navigateur + appareil). Ordre d'execution randomise (`--randomize all`), pour
    debusquer les dependances d'ordre entre tests.

    Chaque test est passe en `--test <nom>` (argument distinct, SANS guillemets) :
    les noms avec espaces, tirets ou accents passent tels quels puisqu'aucun shell
    ne redecoupe la ligne. Si `rerun_failed`, ecrit dans Output_original/ pour
    permettre la fusion ulterieure.
    """
    if rerun_failed:
        report_dir = paths.REPORTS / dt_stamp / "Output_original"
        xml_name, report_name, log_name = "output_original.xml", "report_original.html", "log_original.html"
    else:
        report_dir = paths.REPORTS / dt_stamp
        xml_name, report_name, log_name = "output.xml", "report.html", "log.html"

    cmd = robot_command()
    cmd += ["--randomize", "all"]
    cmd += _listener_arg(session_id)
    for test in tests:
        cmd += ["--test", test]
    cmd += _default_exclusions()
    cmd += ["-d", str(report_dir)]
    cmd += ["-o", xml_name, "-r", report_name, "-l", log_name]
    cmd += ["-v", f"BROWSER:{browser}"]
    cmd += ["-v", f"DEVICE:{device}"]
    cmd += _slow_mo_arg()
    cmd += _tracing_arg()
    cmd += _environment_arg()
    cmd += _actions_arg()
    cmd += ["-N", f"Campaign_Tests_{browser.capitalize()}_{device.capitalize()}"]
    cmd += [str(paths.TEST_SUITES)]

    return cmd


def get_appium_cmd(dt_stamp: str, session_id: str = None) -> list[str]:
    """
    Commande RF pour les tests joues sur un appareil reel, via Appium.

    Deux dossiers sont cibles : `test_suites/appium/` (specifiquement mobile, exclu
    des runs habituels) et `test_suites/multi_moteur/` (ecrit une seule fois, joue ici
    avec l'adaptateur Appium au lieu de Playwright).

    Le serveur Appium doit tourner : c'est l'orchestrateur qui le demarre en amont.
    """
    report_dir = paths.REPORTS / dt_stamp

    cmd = robot_command()
    cmd += _listener_arg(session_id)
    cmd += ["-e", "not_ready", "-e", "in_dev", "-e", "blocked", "-e", "deprecated"]
    cmd += ["-d", str(report_dir)]
    cmd += ["-o", "output.xml", "-r", "report.html", "-l", "log.html"]
    cmd += _environment_arg()
    cmd += _actions_arg('appium')
    cmd += ["-N", "Tests_Mobile_Appium"]
    cmd += [str(paths.TEST_SUITES / 'appium'), str(paths.TEST_SUITES / 'multi_moteur')]

    return cmd
