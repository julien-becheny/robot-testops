"""
Listener Robot Framework pour envoyer les logs d'exécution
vers l'API TestOps en temps réel via HTTP POST.

Usage:
    robot --listener robot_listeners.execution_listener.ExecutionListener:SESSION_ID TestSuites/
"""

import os

import requests

from core.api_config import API_BASE_URL
from core.logging_config import get_logger

logger = get_logger(__name__)

# Les structures de controle (FOR, IF, ITERATION) ne sont pas des etapes de test.
KEYWORD_TYPES = ('KEYWORD', 'SETUP', 'TEARDOWN')
MAX_KEYWORDS_PER_TEST = 80


class ExecutionListener:
    """
    Listener qui envoie les événements d'exécution RF vers l'API locale.
    Les logs sont ensuite broadcastés aux clients via SocketIO.
    Le session_id est passé en argument pour scoper les events.
    """
    ROBOT_LISTENER_API_VERSION = 2

    def __init__(self, session_id='', phase='run'):
        self.ROBOT_LIBRARY_LISTENER = self
        self.session_id = session_id
        self.phase = phase
        # Compter ici evite de deduire le verdict d'une phrase de resume.
        self.counts = {'passed': 0, 'failed': 0, 'skipped': 0}
        self.total_tests = 0
        self.root_suite = ''
        self.kw_depth = 0
        self.kw_sent = 0
        self.in_test = False

    def start_suite(self, name, attrs):
        # Annonce du haut de l'arbre : la suite racine porte le total du run.
        self.total_tests = max(self.total_tests, attrs.get('totaltests', 0) or 0)
        if not self.root_suite:
            self.root_suite = attrs.get('longname') or name

    def end_suite(self, name, attrs):
        self.send_final_status(attrs.get('statistics', ''))

    def start_test(self, name, attrs):
        self.in_test = True
        self.kw_depth = 0
        self.kw_sent = 0
        self.send_log(f"🧪 Test: {name}")

    def start_keyword(self, name, attrs):
        self.kw_depth += 1

    def end_keyword(self, name, attrs):
        """Ne remonte que les etapes ecrites dans le test.

        Chaque notification est un POST bloquant : un test mesure ici jusqu'a
        4500 keywords tous niveaux confondus, contre une dizaine au premier
        niveau. Remonter l'arbre entier ajouterait plus d'une minute au test.
        """
        depth = self.kw_depth
        self.kw_depth -= 1
        if not self.in_test or depth != 1:
            return
        if attrs.get('type') not in KEYWORD_TYPES:
            return

        self.kw_sent += 1
        if self.kw_sent > MAX_KEYWORDS_PER_TEST:
            if self.kw_sent == MAX_KEYWORDS_PER_TEST + 1:
                self.send_log('… etapes suivantes masquees', level='keyword')
            return

        failed = attrs.get('status') not in ('PASS', 'NOT RUN')
        self.send_log(
            attrs.get('kwname') or name,
            level='keyword-failed' if failed else 'keyword',
        )

    def end_test(self, name, attrs):
        self.in_test = False
        status = attrs.get('status', 'UNKNOWN')
        if status == 'PASS':
            self.counts['passed'] += 1
            self.send_log("✅ Le test s'est exécuté avec succès")
        elif status == 'SKIP':
            self.counts['skipped'] += 1
            self.send_log("⏭️ Le test a été ignoré")
        else:
            self.counts['failed'] += 1
            self.send_log("❌ Le test a échoué")
            message = attrs.get('message', '')
            if message:
                self.send_log(f"Message: {message}")
        self.send_test_result(name, attrs)
        self.send_progress()

    def log_file(self, path):
        """Appelé par RF quand log.html est généré (report.html passe par report_file)."""
        log_directory = os.path.dirname(path)
        log_filename = os.path.basename(path)
        self.send_log_link(log_filename)
        self.send_log_directory(log_directory)

    def send_log(self, message, level='info'):
        """Envoie un log vers l'API locale."""
        self._post('/log', {'message': message, 'level': level, 'session_id': self.session_id})

    def send_log_link(self, filename):
        """Envoie le nom du fichier de log vers l'API."""
        self._post('/log-link', {'log_link': filename, 'session_id': self.session_id})

    def send_log_directory(self, directory):
        """Envoie le chemin du dossier de rapports vers l'API."""
        self._post(
            '/log-directory',
            {'log_directory': directory, 'session_id': self.session_id},
        )

    def _test_key(self, name, attrs):
        """Chemin du test debarrasse du nom de la suite racine.

        Ce nom vient de `-N` et porte la configuration du run
        (`Smoke_Test_Firefox_Desktop`) : le garder donnerait a chaque configuration
        ses propres lignes, et la grille comparative n'aurait jamais deux colonnes
        en face du meme test. Le chemin sous la racine, lui, reste stable et
        distingue toujours deux tests homonymes de suites differentes.
        """
        longname = attrs.get('longname') or name
        prefix = f"{self.root_suite}."
        if self.root_suite and longname.startswith(prefix):
            return longname[len(prefix):]
        return longname

    def send_test_result(self, name, attrs):
        """Envoie le verdict d'un test comme une donnee, pas comme une phrase.

        Le chemin complet sert de cle : deux suites peuvent contenir un test
        homonyme, et les confondre ferait fusionner deux lignes distinctes dans
        la grille comparative des configurations.
        """
        self._post(
            '/test-result',
            {
                'name': name,
                'longname': self._test_key(name, attrs),
                'status': attrs.get('status', 'UNKNOWN'),
                'message': attrs.get('message', ''),
                'elapsed': attrs.get('elapsedtime', 0),
                'session_id': self.session_id,
            },
        )

    def send_progress(self):
        """Envoie l'avancement du run : sans lui, seul le chrono bouge."""
        self._post(
            '/progress',
            {
                'done': sum(self.counts.values()),
                'total': self.total_tests,
                'phase': self.phase,
                'session_id': self.session_id,
            },
        )

    def send_final_status(self, statistics):
        """Envoie le statut final de la suite vers l'API."""
        self._post(
            '/final-status',
            {
                'status': statistics,
                'session_id': self.session_id,
                **self.counts,
                'total': sum(self.counts.values()),
            },
        )

    def _post(self, route, payload):
        """Notifie l'API sans laisser une panne réseau interrompre Robot."""
        try:
            response = requests.post(
                f'{API_BASE_URL}{route}',
                json=payload,
                timeout=3,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.debug("Notification listener %s non envoyée : %s", route, exc)
