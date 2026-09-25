"""Index des tests : le contenu de la suite, sous une forme directement interrogeable.

Le rapport de couverture répond « qu'est-ce qui n'a pas de test ? ». Cet index répond la
question inverse, celle qu'on pose dix fois par jour - « quels tests parlent de X ? ».
Sans lui, chaque réponse se paie d'une relecture des suites ; avec lui, elle tient dans un
fichier déjà écrit. Les briques réutilisables (keywords, données, objets) vivent à côté,
dans `catalogue.py` : deux fichiers séparés, pour ne jamais lire l'un en cherchant l'autre.

Deux principes :

- **Rien n'est recalculé autrement.** L'index consomme le même parseur que la couverture
  (`analyzer.collect_code`), donc les deux ne peuvent pas diverger.
- **Une photo dit sa date.** L'index porte l'empreinte de ses sources : un lecteur peut
  savoir qu'il regarde un état périmé au lieu de le croire sur parole. Un index faux et
  muet serait pire que pas d'index du tout.

Le fichier vit dans `results/`, ignoré par git : c'est un dérivé local, jamais un commit.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from core.paths import paths
from services.coverage.analyzer import (
    Referentiel,
    collect_code,
    declared_features,
    load_referentiel,
    reachable_screens,
)
from services.coverage.freshness import fingerprint
from services.coverage.freshness import is_stale as _is_stale

INDEX_PATH = paths.RESULTS / "tests_index.json"

# À incrémenter dès que la structure d'une entrée change : sans ça, un index produit par
# l'ancien format resterait en place, ses sources étant inchangées.
FORMAT = 2


# --- Sources ---------------------------------------------------------------
def _source_files(suites_dir: Path, resources_dir: Path, map_dir: Path) -> list[Path]:
    return sorted(
        [
            *suites_dir.rglob("*.robot"),
            *resources_dir.rglob("*.resource"),
            *map_dir.glob("*.yaml"),
            *map_dir.glob("*.yml"),
        ]
    )


# --- Construction ----------------------------------------------------------
def _searchable_text(
    name: str, doc: str, features: list[str], screens: list[str], ref: Referentiel
) -> str:
    """Le test dit en français : son nom, sa documentation, les libellés du référentiel.

    Champ prévu pour une recherche par le sens (embedding local) le jour où elle servira ;
    utile dès aujourd'hui pour une recherche par mots.
    """
    parts = [name]
    if doc:
        parts.append(doc)
    parts += [ref.fonctionnalites[f].label for f in features if f in ref.fonctionnalites]
    parts += [ref.ecrans[s].label for s in screens if s in ref.ecrans]
    return " · ".join(parts)


def build_index(
    suites_dir: Path | None = None,
    resources_dir: Path | None = None,
    map_dir: Path | None = None,
) -> dict:
    suites_dir = suites_dir or paths.TEST_SUITES
    resources_dir = resources_dir or paths.RESOURCES
    map_dir = map_dir or paths.FUNCTIONAL_MAP

    ref = load_referentiel(map_dir)
    tests, keywords, _ = collect_code(suites_dir, resources_dir)

    entries = []
    for test in tests:
        features = declared_features(test)
        screens = sorted(reachable_screens(test, keywords))
        entries.append(
            {
                "nom": test.name,
                "fichier": test.source,
                "ligne": test.line,
                "doc": test.doc,
                "tags": sorted(set(test.tags)),
                "feat": features,
                "ecrans": screens,
                "keywords": test.calls_raw,
                "texte": _searchable_text(test.name, test.doc, features, screens, ref),
            }
        )

    return {
        "genere_le": datetime.now().isoformat(timespec="seconds"),
        "format": FORMAT,
        "sources": fingerprint(_source_files(suites_dir, resources_dir, map_dir)),
        "tests": sorted(entries, key=lambda entry: (entry["fichier"], entry["ligne"])),
    }


# --- Persistance -----------------------------------------------------------
def write_index(index: dict, path: Path | None = None) -> Path:
    path = path or INDEX_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_index(path: Path | None = None) -> dict | None:
    """L'index lu, ou None s'il est absent ou illisible (écriture interrompue)."""
    path = path or INDEX_PATH
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def is_stale(
    index: dict,
    suites_dir: Path | None = None,
    resources_dir: Path | None = None,
    map_dir: Path | None = None,
) -> bool:
    """Vrai si une source a changé, disparu ou été ajoutée depuis la génération."""
    return _is_stale(
        index,
        _source_files(
            suites_dir or paths.TEST_SUITES,
            resources_dir or paths.RESOURCES,
            map_dir or paths.FUNCTIONAL_MAP,
        ),
        FORMAT,
    )


def refresh_index(path: Path | None = None) -> tuple[Path, dict, bool]:
    """Régénère l'index si ses sources ont bougé. Retourne (chemin, index, régénéré)."""
    path = path or INDEX_PATH
    existing = load_index(path)
    if existing is not None and not is_stale(existing):
        return path, existing, False
    index = build_index()
    return write_index(index, path), index, True
