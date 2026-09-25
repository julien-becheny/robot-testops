#!/usr/bin/env python
"""Contrôles qualité du dépôt - source de vérité unique, locale et CI.

    uv run tools/ci_local.py           # les contrôles
    uv run tools/ci_local.py --full    # + `npm ci` (réinstalle node_modules)
    uv run tools/ci_local.py --verbose # + la sortie des contrôles qui passent

Le workflow GitHub appelle ce même script : ce qui tourne en CI est ce qui tourne en
local **par construction**, et non par discipline. Le YAML ne garde que la préparation
de la machine (checkout, Python, Node, installation des dépendances).

Tous les contrôles sont exécutés, même après un échec : on veut la photo complète en
une passe plutôt qu'un aller-retour par problème.

Seuls les contrôles en échec impriment leur sortie. Un vert n'apprend rien de plus que
son icône, et cette sortie est relue à chaque tour quand un agent lance le script.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TESTOPS_DIR = REPO_ROOT / "testops"

# Un audit npm qui ne joint pas le registre (proxy d'entreprise, coupure) renvoie 1,
# exactement comme une vulnérabilité. « Audit impossible » n'est pas « audit rouge ».
_NETWORK_MARKERS = (
    "econnreset",
    "enotfound",
    "etimedout",
    "econnrefused",
    "eai_again",
    "audit endpoint returned an error",
    "request to https://registry.npmjs.org",
)

OK, FAILED, SKIPPED = "ok", "failed", "skipped"
ICONS = {OK: "✓", FAILED: "✖", SKIPPED: "•"}


@dataclass
class Step:
    """Un contrôle : un nom lisible et une commande en liste d'arguments (SHELL_STR)."""

    name: str
    argv: list[str]
    cwd: Path = REPO_ROOT
    tolerate_network_failure: bool = False


def _npm(*args: str) -> list[str]:
    """Sous Windows, `npm` est un shim `.cmd` que CreateProcess ne sait pas lancer seul."""
    if os.name == "nt":
        return ["cmd", "/c", "npm", *args]
    return ["npm", *args]


def build_steps(full: bool = False) -> list[Step]:
    """Les contrôles, dans l'ordre : Python d'abord (rapide), frontend ensuite."""
    # `--locked` refuse un verrou périmé par rapport à pyproject.toml, `--check` un
    # environnement qui a dérivé du verrou. Aucun des deux ne modifie quoi que ce soit.
    steps = [Step("Environnement Python conforme au verrou",
                  ["uv", "sync", "--locked", "--check"])]

    if full:
        steps.append(Step("Dépendances frontend (lockfile)", _npm("ci"), cwd=TESTOPS_DIR))

    steps += [
        Step("Tests unitaires Python", [sys.executable, "-m", "pytest", "unit_tests", "-q"]),
        Step("Analyse statique Robot Framework",
             [sys.executable, "-m", "robotcode.cli", "analyze", "code"]),
        Step("Références de couverture fonctionnelle",
             [sys.executable, str(REPO_ROOT / "tools" / "coverage.py"), "--check"]),
        Step("ESLint", _npm("run", "lint"), cwd=TESTOPS_DIR),
        Step("Tests frontend", _npm("run", "test:ci"), cwd=TESTOPS_DIR),
        Step("Format frontend", _npm("run", "format:check"), cwd=TESTOPS_DIR),
        Step("Build frontend", _npm("run", "build"), cwd=TESTOPS_DIR),
        Step("Audit des dépendances de production",
             _npm("audit", "--omit=dev", "--audit-level=low"),
             cwd=TESTOPS_DIR, tolerate_network_failure=True),
    ]
    return steps


def is_network_failure(output: str) -> bool:
    """Distingue « le registre est injoignable » de « une vulnérabilité est trouvée »."""
    lowered = output.lower()
    return any(marker in lowered for marker in _NETWORK_MARKERS)


def _force_utf8() -> None:
    """Évite les UnicodeEncodeError sous Windows (console cp1252, sortie redirigée)."""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(encoding="utf-8", errors="replace")


def run_step(step: Step, index: int, total: int, verbose: bool = False) -> str:
    print(f"── [{index}/{total}] {step.name} " + "─" * max(4, 50 - len(step.name)) + " ",
          end="", flush=True)

    done = subprocess.run(step.argv, cwd=step.cwd, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    output = done.stdout + done.stderr

    if done.returncode == 0:
        status = OK
    elif step.tolerate_network_failure and is_network_failure(output):
        status = SKIPPED
    else:
        status = FAILED

    print(ICONS[status], flush=True)
    if status == SKIPPED:
        print("   → Registre injoignable : audit non concluant, contrôle ignoré.")
    if verbose or status == FAILED:
        sys.stdout.write("\n" + output.rstrip() + "\n")
    return status


def main() -> int:
    _force_utf8()
    parser = argparse.ArgumentParser(description="Contrôles qualité du dépôt.")
    parser.add_argument("--full", action="store_true",
                        help="inclut `npm ci` (efface et réinstalle node_modules)")
    parser.add_argument("--verbose", action="store_true",
                        help="affiche aussi la sortie des contrôles qui passent")
    args = parser.parse_args()

    if shutil.which("uv") is None:
        print("uv est introuvable dans le PATH - voir la section Démarrage du README.")
        return 1

    steps = build_steps(args.full)
    results = [(step.name, run_step(step, i, len(steps), args.verbose))
               for i, step in enumerate(steps, start=1)]

    print("\n" + "=" * 62)
    print("RÉCAPITULATIF")
    for name, status in results:
        print(f"  {ICONS[status]} {name}")

    failed = [name for name, status in results if status == FAILED]
    if failed:
        print(f"\n{len(failed)} contrôle(s) en échec : {', '.join(failed)}\n")
        return 1
    print("\nTous les contrôles sont verts.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
