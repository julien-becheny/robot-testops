"""Catalogue des briques réutilisables : keywords, données de test, objets d'interface.

Répond à la question qu'il faut se poser **avant** d'écrire un test : *qu'est-ce qui
existe déjà ?* Sans elle, on réinvente un keyword qui existe, on recrée une donnée, on
invente une clé de locator - et le test produit ne compile pas, ou double une brique.

Ne contient que le **contrat** de chaque brique : son nom, ses arguments, son résumé, son
emplacement. Jamais le corps. Le corps représente l'essentiel du volume et n'apprend rien
sur la façon d'appeler ; s'il faut le lire, `fichier:ligne` y mène directement.

Deux conséquences de ce parti pris :

- le catalogue reste petit - de l'ordre de 250 octets par brique ;
- il grandit quand même avec le dépôt, et **se consulte par recherche**, pas d'un bloc.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import yaml

from core.paths import paths
from services.coverage.analyzer import CodeUnit, _rel, collect_keyword_definitions
from services.coverage.freshness import fingerprint
from services.coverage.freshness import is_stale as _is_stale

CATALOGUE_PATH = paths.RESULTS / "catalogue.json"

# À incrémenter dès que la structure d'une brique change (cf. `freshness.is_stale`).
FORMAT = 1

PARTAGEE = "partagee"
SUITE = "suite"


# --- Keywords --------------------------------------------------------------
def _portee(source: str) -> str:
    """Un keyword défini dans un `.robot` n'est visible que dans ce fichier.

    L'ignorer ferait proposer des appels qui ne résolvent pas - c'est une information de
    justesse, pas de confort.
    """
    return PARTAGEE if source.endswith(".resource") else SUITE


def _resume(doc: str) -> str:
    """La première ligne de la documentation : par convention Robot, c'est le résumé."""
    return doc.strip().splitlines()[0].strip() if doc.strip() else ""


def _keyword_payload(keyword: CodeUnit) -> dict:
    return {
        "nom": keyword.name,
        "fichier": keyword.source,
        "ligne": keyword.line,
        "args": keyword.args,
        "doc": _resume(keyword.doc),
        "portee": _portee(keyword.source),
    }


# --- Données et objets -----------------------------------------------------
def _chemins(valeur: object, prefixe: str) -> list[str]:
    """Les chemins d'accès d'une structure YAML, sans ses valeurs.

    Une liste est réduite à son premier élément, marqué `[]` : connaître la forme suffit
    pour écrire un accès, et recopier trois cents entrées n'apprendrait rien de plus.
    """
    if isinstance(valeur, dict):
        chemins: list[str] = []
        for cle, sous_valeur in valeur.items():
            chemin = f"{prefixe}.{cle}" if prefixe else str(cle)
            chemins += _chemins(sous_valeur, chemin)
        return chemins
    if isinstance(valeur, list):
        return _chemins(valeur[0], f"{prefixe}[]") if valeur else [f"{prefixe}[]"]
    return [prefixe]


def _fichiers_yaml(dossier: Path) -> list[Path]:
    return sorted([*dossier.rglob("*.yml"), *dossier.rglob("*.yaml")])


def _structures(dossier: Path) -> list[dict]:
    """Une entrée par variable Robot déclarée dans les YAML du dossier."""
    entrees = []
    for path in _fichiers_yaml(dossier):
        contenu = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(contenu, dict):
            continue
        for variable, valeur in contenu.items():
            entrees.append(
                {
                    "variable": str(variable),
                    "fichier": _rel(path),
                    "cles": _chemins(valeur, ""),
                }
            )
    return entrees


# --- Construction ----------------------------------------------------------
def _sources(
    suites_dir: Path, resources_dir: Path, data_dir: Path, objects_dir: Path
) -> list[Path]:
    return sorted(
        [
            *suites_dir.rglob("*.robot"),
            *resources_dir.rglob("*.resource"),
            *_fichiers_yaml(data_dir),
            *_fichiers_yaml(objects_dir),
        ]
    )


def build_catalogue(
    suites_dir: Path | None = None,
    resources_dir: Path | None = None,
    data_dir: Path | None = None,
    objects_dir: Path | None = None,
) -> dict:
    suites_dir = suites_dir or paths.TEST_SUITES
    resources_dir = resources_dir or paths.RESOURCES
    data_dir = data_dir or paths.TEST_DATA
    objects_dir = objects_dir or paths.TEST_OBJECTS

    keywords = collect_keyword_definitions(suites_dir, resources_dir)
    return {
        "genere_le": datetime.now().isoformat(timespec="seconds"),
        "format": FORMAT,
        "sources": fingerprint(_sources(suites_dir, resources_dir, data_dir, objects_dir)),
        "keywords": sorted(
            (_keyword_payload(keyword) for keyword in keywords),
            key=lambda entree: (entree["fichier"], entree["ligne"]),
        ),
        "donnees": _structures(data_dir),
        "objets": _structures(objects_dir),
    }


# --- Persistance -----------------------------------------------------------
def write_catalogue(catalogue: dict, path: Path | None = None) -> Path:
    path = path or CATALOGUE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalogue, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_catalogue(path: Path | None = None) -> dict | None:
    path = path or CATALOGUE_PATH
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def is_stale(
    catalogue: dict,
    suites_dir: Path | None = None,
    resources_dir: Path | None = None,
    data_dir: Path | None = None,
    objects_dir: Path | None = None,
) -> bool:
    return _is_stale(
        catalogue,
        _sources(
            suites_dir or paths.TEST_SUITES,
            resources_dir or paths.RESOURCES,
            data_dir or paths.TEST_DATA,
            objects_dir or paths.TEST_OBJECTS,
        ),
        FORMAT,
    )


def refresh_catalogue(path: Path | None = None) -> tuple[Path, dict, bool]:
    """Régénère le catalogue si ses sources ont bougé. Retourne (chemin, catalogue, régénéré)."""
    path = path or CATALOGUE_PATH
    existant = load_catalogue(path)
    if existant is not None and not is_stale(existant):
        return path, existant, False
    catalogue = build_catalogue()
    return write_catalogue(catalogue, path), catalogue, True
