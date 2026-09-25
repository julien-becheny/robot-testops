#!/usr/bin/env python
"""Couverture fonctionnelle en ligne de commande.

La logique vit dans `services/coverage/` (consommée aussi par l'API) ; ce script
n'est que l'entrée console.

Usage :
  python tools/coverage.py            # écrit le JSON + le HTML partageable, puis résume
  python tools/coverage.py --check    # ne génère rien ; sort en erreur sur référence inconnue
  python tools/coverage.py --index    # met à jour l'index et le catalogue s'ils sont périmés
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.paths import paths  # noqa: E402
from services.coverage import analyse, refresh_catalogue, refresh_index, write_html  # noqa: E402
from services.coverage.analyzer import Finding  # noqa: E402

_LEVEL_ICON = {"error": "✖", "warning": "▲"}


def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _rel(path: Path) -> str:
    return path.resolve().relative_to(paths.PROJECT_ROOT).as_posix()


def _print_findings(findings: list[Finding]) -> None:
    print()
    for finding in findings:
        icon = _LEVEL_ICON.get(finding.level, "·")
        print(f"  {icon} {finding.location}  [{finding.code}] {finding.message}")
    print()


def _print_summary(report: dict) -> None:
    print("\n=== Couverture fonctionnelle ===\n")
    for module in report["modules"]:
        print(f"── {module['label']} ({module['id']})")
        for key, label in (("ecrans", "Écrans et popups"), ("fonctionnalites", "Fonctionnalités")):
            missing = [e for e in module[key] if e["statut"] == "non_couvert"]
            if not missing:
                print(f"   {label} : aucun sans test.")
                continue
            print(f"   {label} sans test :")
            for entry in missing:
                print(f"      · {entry['label']}  ({entry['id']})")
        print()
    scope = report["perimetre"]
    print(
        f"Référentiel : {scope['ecrans']} écrans et popups, "
        f"{scope['fonctionnalites']} fonctionnalités décrits. "
        "Ce qui n'y figure pas n'est pas évalué.\n"
    )


def run(check_only: bool) -> int:
    report, findings = analyse()
    errors = [f for f in findings if f.level == "error"]
    if findings:
        _print_findings(findings)
    if errors:
        print(f"→ {len(errors)} référence(s) invalide(s) : le rapport n'est pas fiable.\n")
        return 1
    if check_only:
        print("Couverture : toutes les références sont valides.\n")
        return 0

    json_path = paths.RESULTS / "functional_coverage.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path = write_html(report)

    _print_summary(report)
    print(f"Rapport partageable : {_rel(html_path)}")
    print(f"Données            : {_rel(json_path)}")
    run_index()
    return 0


def run_index() -> int:
    """L'index des tests et le catalogue, régénérés seulement si une source a bougé."""
    path, index, regenerated = refresh_index()
    etat = "régénéré" if regenerated else "déjà à jour"
    print(f"Index des tests {etat} : {len(index['tests'])} tests - {_rel(path)}")

    path, catalogue, regenerated = refresh_catalogue()
    etat = "régénéré" if regenerated else "déjà à jour"
    briques = len(catalogue["keywords"]) + len(catalogue["donnees"]) + len(catalogue["objets"])
    print(f"Catalogue {etat} : {briques} briques - {_rel(path)}\n")
    return 0


def main() -> int:
    _force_utf8()
    parser = argparse.ArgumentParser(description="Couverture fonctionnelle (TestOps).")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="vérifie les références sans générer de rapport (hook de commit, CI)",
    )
    mode.add_argument(
        "--index",
        action="store_true",
        help="met à jour l'index des tests et le catalogue (hook de commit)",
    )
    args = parser.parse_args()
    if args.index:
        return run_index()
    return run(check_only=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
