"""Fraîcheur des artefacts dérivés du code.

Un artefact périmé et muet est pire que pas d'artefact : on lui fait confiance. Chacun
porte donc l'empreinte de ses sources, et sait dire qu'il ne décrit plus le dépôt.

L'empreinte porte sur le **contenu**, jamais sur la date de modification : un `git clone`,
une copie ou une synchronisation réécrivent les dates sans toucher au contenu. Un contrôle
par date crierait à chaque fois - et une alerte qu'on apprend à ignorer ne protège de rien.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from services.coverage.analyzer import _rel


def fingerprint(files: list[Path]) -> dict[str, str]:
    return {_rel(path): hashlib.sha256(path.read_bytes()).hexdigest()[:16] for path in files}


def is_stale(artefact: dict, files: list[Path], format_version: int) -> bool:
    """Vrai si une source a bougé, ou si l'artefact a été produit par un format antérieur.

    La version du format est le second garde-fou, et il n'est pas théorique : changer la
    structure d'un artefact sans toucher aux sources laissait l'ancien fichier en place,
    déclaré « à jour ». Un lecteur y aurait cherché des champs disparus.
    """
    if artefact.get("format") != format_version:
        return True
    return artefact.get("sources") != fingerprint(files)
