"""
Preflight mobile : verifie que la chaine Appium est prete avant un run mobile.

Reutilise par :
  - le setup (CLI : ``python -m services.mobile.preflight``),
  - l'API (``GET /mobile-preflight``),
  - le log de demarrage du backend.

Aucune dependance a Robot Framework : juste subprocess / requests / core.config.
Chaque check = {name, ok (True|False|None=N/A), detail, hint}.
"""

# Standard library
import os
import shutil
import subprocess
from pathlib import Path

# Third-party
import requests

# Local/projet
from core import config

_IOS_PLATFORMS = ("ios", "iphone", "ipad")


def _which(name):
    """Chemin d'un executable resolu via le PATH (gere .cmd/.exe sous Windows)."""
    return shutil.which(name)


def _run_tool(path, args, timeout=20):
    """Execute un outil ; gere les shims .cmd Windows (appium, npm) via `cmd /c`.

    CreateProcess ne sait pas lancer un .cmd directement : il faut passer par
    l'interpreteur. On le fait en LISTE (`cmd /c <exe> <args>`) et non en chaine
    avec shell=True : les arguments restent separes, donc pas de quoting manuel
    ni de reinterpretation. Regle SHELL_STR - docs/regles_apprises.md.
    """
    try:
        if os.name == "nt" and path.lower().endswith(".cmd"):
            proc = subprocess.run(["cmd", "/c", path, *args], capture_output=True,
                                  text=True, timeout=timeout, encoding="utf-8", errors="replace")
        else:
            proc = subprocess.run([path, *args], capture_output=True, text=True,
                                  timeout=timeout, encoding="utf-8", errors="replace")
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except (OSError, subprocess.SubprocessError):
        return -1, ""


def _adb_path():
    """adb depuis le PATH, sinon ANDROID_HOME / ANDROID_SDK_ROOT / platform-tools."""
    found = _which("adb")
    if found:
        return found
    # Frontière système : ces variables sont définies par l'installateur Android,
    # avec repli sur core.config pour les postes configurés depuis TestOps.
    for var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        root = os.environ.get(var) or config.get(var)
        if root:
            exe = "adb.exe" if os.name == "nt" else "adb"
            candidate = Path(root) / "platform-tools" / exe
            if candidate.exists():
                return str(candidate)
    return None


def _check(name, ok, detail, hint=""):
    return {"name": name, "ok": ok, "detail": detail, "hint": hint}


def _check_appium_cli():
    path = _which("appium")
    if not path:
        return _check("Serveur Appium (CLI)", False, "binaire `appium` introuvable",
                      "npm install -g appium")
    return _check("Serveur Appium (CLI)", True, path)


def _check_appium_server():
    url = (config.get("RF_APPIUM_URL", "http://127.0.0.1:4723") or "").rstrip("/")
    try:
        resp = requests.get(f"{url}/status", timeout=4)
        return _check("Serveur Appium (en ligne)", resp.ok, f"{url} (HTTP {resp.status_code})",
                      "" if resp.ok else "Lancer : appium")
    except requests.RequestException:
        return _check("Serveur Appium (en ligne)", False, f"injoignable ({url})", "Lancer : appium")


def _check_appium_driver(driver):
    path = _which("appium")
    if not path:
        return _check(f"Driver Appium {driver}", None, "appium introuvable")
    code, out = _run_tool(path, ["driver", "list", "--installed"])
    if code != 0:
        return _check(f"Driver Appium {driver}", None, "liste des drivers indisponible")
    installed = driver in out
    return _check(f"Driver Appium {driver}", installed, "installe" if installed else "absent",
                  "" if installed else f"appium driver install {driver}")


def _check_android_device():
    adb = _adb_path()
    if not adb:
        return _check("Android SDK (adb)", False, "adb introuvable",
                      "Installer Android SDK + platform-tools et definir ANDROID_HOME")
    code, out = _run_tool(adb, ["devices"])
    if code != 0:
        return _check("Appareil Android", False, "echec de `adb devices`")
    devices = [line.split("\t")[0] for line in out.splitlines()[1:] if "\tdevice" in line]
    if not devices:
        return _check("Appareil Android", False, "aucun appareil / emulateur detecte",
                      "Brancher un telephone (debogage USB) ou lancer un emulateur")
    return _check("Appareil Android", True, ", ".join(devices))


def check_mobile_env(platform=None):
    """Etat de la chaine mobile : {ok, platform, checks:[...]}. `ok` ignore les N/A."""
    platform = (platform or config.get("RF_MOBILE_PLATFORM") or "Android").strip().lower()
    server = _check_appium_server()
    checks = [_check_appium_cli(), server]

    if platform in _IOS_PLATFORMS:
        if os.name == "nt":
            checks.append(_check("iOS", None, "non pilotable depuis Windows (Mac + Xcode requis)"))
        else:
            checks.append(_check_appium_driver("xcuitest"))
    else:
        checks.append(_check_android_device())
        checks.append(_check_appium_driver("uiautomator2"))

    ok = all(c["ok"] for c in checks if c["ok"] is not None)
    return {"ok": ok, "platform": platform, "appium_online": bool(server["ok"]), "checks": checks}


def summary_lines(result):
    """Rendu texte (CLI / log de demarrage)."""
    icon = {True: "OK", False: "KO", None: "--"}
    header = f"Mobile ({result['platform']}) : {'PRET' if result['ok'] else 'INCOMPLET'}"
    lines = [header]
    for c in result["checks"]:
        line = f"  [{icon[c['ok']]}] {c['name']} : {c['detail']}"
        if c["ok"] is False and c["hint"]:
            line += f"  -> {c['hint']}"
        lines.append(line)
    return lines


def main():
    """Affiche le diagnostic CLI et retourne un code compatible avec les scripts setup."""
    result = check_mobile_env()
    for line in summary_lines(result):
        print(line)  # cli-output-ok: sortie utilisateur volontaire du préflight
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
