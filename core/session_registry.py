"""
Registre central des sessions d'exécution.

Chaque exécution (test lancé depuis l'UI) est identifiée par un session_id unique.
Cela permet de lancer plusieurs exécutions en parallèle (multi-navigateur, etc.)
avec des logs, rapports et stop signals isolés.
"""

import re
import threading
import uuid
from dataclasses import dataclass, fields, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from core.paths import paths

SESSION_STATUSES = frozenset({'pending', 'running', 'completed', 'stopped'})
_SESSION_ID_PATTERN = re.compile(r'^[A-Za-z0-9_-]+$')


@dataclass
class ExecutionSession:
    """État d'une session d'exécution individuelle."""
    session_id: str
    browser: str = 'chromium'
    workflow: str = ''
    status: str = 'pending'          # pending | running | completed | stopped
    started_at: datetime | None = None
    started_by_ip: str | None = None
    process: object | None = None  # subprocess.Popen
    dt_stamp: str = ''
    exit_code: int | None = None
    report_folder: str = ''
    log_directory: str = ''


_UPDATABLE_FIELDS = frozenset(
    field.name for field in fields(ExecutionSession) if field.name != 'session_id'
)


class SessionRegistry:
    """
    Registry thread-safe pour gérer N sessions d'exécution en parallèle.
    Singleton — une seule instance partagée par tout le backend.
    """
    _instance = None
    _instance_lock = threading.Lock()
    # Declares ici, et non dans __new__ : une annotation portee par `cls._instance._x`
    # est evaluee puis jetee (PEP 526), donc elle ne type rien.
    _sessions: dict[str, ExecutionSession]
    _lock: threading.RLock

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._sessions = {}
                    cls._instance._lock = threading.RLock()
        return cls._instance

    def create_session(self, browser: str = 'chromium', workflow: str = '',
                       started_by_ip: str | None = None) -> ExecutionSession:
        """Crée une session unique et retourne un instantané indépendant."""
        with self._lock:
            session_id = self._new_session_id()
            session = ExecutionSession(
                session_id=session_id,
                browser=browser,
                workflow=workflow,
                status='pending',
                started_at=datetime.now(),
                started_by_ip=started_by_ip,
            )
            self._sessions[session_id] = session
            return replace(session)

    def _new_session_id(self) -> str:
        """Génère un identifiant court absent du registre déjà verrouillé."""
        while True:
            session_id = uuid.uuid4().hex[:8]
            if session_id not in self._sessions:
                return session_id

    def get(self, session_id: str) -> ExecutionSession | None:
        """Retourne un instantané d'une session, ou ``None`` si elle est absente."""
        with self._lock:
            session = self._sessions.get(session_id)
            return replace(session) if session else None

    def update(self, session_id: str, **kwargs: Any) -> bool:
        """Met à jour atomiquement les champs autorisés d'une session.

        Returns:
            ``True`` si la session existe et a été mise à jour, sinon ``False``.

        Raises:
            ValueError: Si un champ ou un statut n'appartient pas au contrat.
        """
        unknown_fields = set(kwargs) - _UPDATABLE_FIELDS
        if unknown_fields:
            raise ValueError(
                f"Champs de session inconnus : {', '.join(sorted(unknown_fields))}"
            )
        if 'status' in kwargs and kwargs['status'] not in SESSION_STATUSES:
            raise ValueError(f"Statut de session invalide : {kwargs['status']}")

        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False
            for key, value in kwargs.items():
                setattr(session, key, value)
            return True

    def remove(self, session_id: str) -> bool:
        """Supprime une session et indique si elle existait."""
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def get_all(self) -> dict[str, ExecutionSession]:
        """Retourne un instantané indépendant de toutes les sessions."""
        with self._lock:
            return {session_id: replace(session) for session_id, session in self._sessions.items()}

    def get_running(self) -> dict[str, ExecutionSession]:
        """Retourne des instantanés des sessions en cours."""
        with self._lock:
            return {
                session_id: replace(session)
                for session_id, session in self._sessions.items()
                if session.status == 'running'
            }

    def count_running(self) -> int:
        """Nombre de sessions en cours."""
        with self._lock:
            return sum(session.status == 'running' for session in self._sessions.values())

    def stop_signal_path(self, session_id: str) -> Path:
        """Retourne un stop signal sous ``temp`` pour un identifiant sûr."""
        if not _SESSION_ID_PATTERN.fullmatch(session_id):
            raise ValueError("Identifiant de session invalide")
        return paths.TEMP / f"stop_signal_{session_id}.txt"


# Instance globale
registry = SessionRegistry()
