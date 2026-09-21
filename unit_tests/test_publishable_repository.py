"""Le dépôt est public : rien de ce qui est versionné ne doit nommer le poste qui l'a produit.

Cas réel à l'origine de ce contrôle : Robot Framework écrit dans `log.html` le chemin
absolu des suites jouées. Le rapport embarqué dans la démonstration portait donc le nom
du compte Windows, six fois, prêt à partir en ligne.
"""

import os
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

TEXT_SUFFIXES = {
    ".py", ".js", ".jsx", ".json", ".md", ".yaml", ".yml", ".robot", ".resource",
    ".toml", ".html", ".css", ".sh", ".bat", ".txt", ".example",
}


def current_account() -> str:
    """Le compte qui fait tourner les tests - celui dont le nom ne doit pas fuiter."""
    return os.environ.get("USERNAME") or os.environ.get("USER") or ""


def tracked_files() -> list[Path]:
    """Les fichiers réellement versionnés : ce que le monde peut lire."""
    listing = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", check=False,
    )
    return [Path(line) for line in listing.stdout.splitlines() if line]


def files_matching(pattern: re.Pattern) -> list[str]:
    """Retourne les fichiers versionnés dont le contenu correspond au motif."""
    hits = []
    for relative in tracked_files():
        if relative.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            content = (REPO_ROOT / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if pattern.search(content):
            hits.append(relative.as_posix())
    return hits


def home_directory_pattern(account: str) -> re.Pattern:
    """Le compte en position de dossier personnel, seule forme qui trahisse une machine.

    Chercher le nom seul serait ingérable : sur un exécuteur d'intégration continue il
    vaut « runner », mot que ce dépôt emploie partout. Les doubles antislashs couvrent
    les chemins Windows échappés dans un fichier généré (`C:\\\\Users\\\\…`).
    """
    return re.compile(rf"(?:Users|home)[\\/]{{1,2}}{re.escape(account)}", re.IGNORECASE)


def test_no_tracked_file_exposes_the_local_home_directory() -> None:
    """Aucun fichier publié ne doit contenir le dossier personnel du compte courant."""
    account = current_account()
    if len(account) < 3:
        return  # Un nom trop court produirait des correspondances fortuites.

    offenders = files_matching(home_directory_pattern(account))

    assert not offenders, (
        f"le dossier personnel de « {account} » apparaît dans des fichiers publiés :\n"
        + "\n".join(offenders)
    )


def test_the_check_still_bites(tmp_path: Path) -> None:
    """Un contrôle qui ne trouve plus rien doit rester un contrôle qui cherche encore."""
    report = tmp_path / "log.html"
    report.write_text(r'"source":"C:\\Users\\jdupont\\tests"', encoding="utf-8")
    content = report.read_text(encoding="utf-8")

    assert home_directory_pattern("jdupont").search(content)
    assert home_directory_pattern("jdupont").search("/home/jdupont/projet")
    # Le nom cité hors chemin ne dit rien de la machine : « runner » est ici un métier.
    assert not home_directory_pattern("runner").search("from services.execution.runner")
    assert tracked_files(), "sans fichier suivi, le contrôle passerait toujours"
