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
    """Le compte qui fait tourner les tests — celui dont le nom ne doit pas fuiter."""
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


def test_no_tracked_file_names_the_local_account() -> None:
    """Le nom du compte courant ne doit apparaître dans aucun fichier publié."""
    account = current_account()
    if len(account) < 4:
        return  # Un nom trop court produirait des correspondances fortuites.

    offenders = files_matching(re.compile(re.escape(account), re.IGNORECASE))

    assert not offenders, (
        f"le compte « {account} » est nommé dans des fichiers publiés :\n"
        + "\n".join(offenders)
    )


def test_the_check_still_bites(tmp_path: Path) -> None:
    """Un contrôle qui ne trouve plus rien doit rester un contrôle qui cherche encore."""
    report = tmp_path / "log.html"
    report.write_text(r'"source":"C:\\Users\\jdupont\\tests"', encoding="utf-8")
    pattern = re.compile(re.escape("jdupont"), re.IGNORECASE)

    assert pattern.search(report.read_text(encoding="utf-8"))
    assert not pattern.search("aucun nom de compte ici")
    assert tracked_files(), "sans fichier suivi, le contrôle passerait toujours"
