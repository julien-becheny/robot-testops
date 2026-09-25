"""
Cycle de vie du serveur Appium gere par TestOps.

Objectif : demarrer Appium *a la demande* (bouton UI ou 1er run mobile) et
l'arreter proprement, plutot qu'un process orphelin lance par un .bat. Rien ne
tourne en session 100 % web.

- ``start()``  : lance le serveur (non bloquant) s'il n'est pas deja en ligne.
- ``stop()``   : arrete le serveur lance par TestOps (tue l'arbre de process).
- ``is_running()`` : ping ``{RF_APPIUM_URL}/status``.
Le PID gere est un singleton module ; ``atexit`` nettoie a l'arret du backend.
"""

# Standard library
import atexit
import os
import shutil
import signal
import subprocess
import threading
from urllib.parse import urlparse

# Third-party
import requests

# Local/projet
from core import config

_lock = threading.Lock()
_managed_pid = None  # PID du serveur Appium lance par TestOps (None si externe/arrete)


def _appium_path():
    return shutil.which("appium")


def _base_url():
    return (config.get("RF_APPIUM_URL", "http://127.0.0.1:4723") or "").rstrip("/")


def _host_port():
    parsed = urlparse(_base_url())
    return (parsed.hostname or "127.0.0.1"), (parsed.port or 4723)


def is_running(timeout=3):
    """True si un serveur Appium repond sur RF_APPIUM_URL/status."""
    try:
        return requests.get(f"{_base_url()}/status", timeout=timeout).ok
    except requests.RequestException:
        return False


def start():
    """Demarre le serveur Appium (non bloquant). No-op s'il est deja en ligne."""
    global _managed_pid
    if is_running():
        return {"ok": True, "running": True, "detail": "serveur deja en ligne"}

    path = _appium_path()
    if not path:
        return {"ok": False, "running": False, "detail": "binaire appium introuvable",
                "hint": "npm install -g appium"}

    host, port = _host_port()
    with _lock:
        try:
            if os.name == "nt":
                # Nouvelle console MINIMISEE (comme Flask/React) ; pid trackable via `cmd /c`
                # qui reste vivant tant qu'Appium tourne -> taskkill /T tue cmd + node.
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 7  # SW_SHOWMINNOACTIVE : minimisee, sans voler le focus
                proc = subprocess.Popen(
                    ["cmd", "/c", path, "--address", host, "--port", str(port), "--relaxed-security"],
                    creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=startupinfo)
            else:
                proc = subprocess.Popen(
                    [path, "--address", host, "--port", str(port), "--relaxed-security"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=True)
        except (OSError, subprocess.SubprocessError) as exc:
            return {"ok": False, "running": False, "detail": f"echec du demarrage : {exc}"}
        _managed_pid = proc.pid

    return {"ok": True, "running": False,
            "detail": "demarrage lance - le serveur sera en ligne dans quelques secondes"}


def stop():
    """Arrete le serveur Appium lance par TestOps (tue l'arbre de process)."""
    global _managed_pid
    if _managed_pid is None:
        if is_running():
            return {"ok": False,
                    "detail": "serveur en ligne mais non lance par TestOps - arret manuel requis"}
        return {"ok": True, "detail": "aucun serveur gere par TestOps"}

    pid = _managed_pid
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                           capture_output=True, text=True)
        else:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "detail": f"echec de l'arret : {exc}"}

    _managed_pid = None
    return {"ok": True, "detail": "serveur Appium arrete"}


@atexit.register
def _cleanup_on_exit():
    """Arrete le serveur Appium gere quand le backend s'arrete (best effort)."""
    if _managed_pid is not None:
        stop()
