"""
Rapport agrege d'une campagne : combine les `output.xml` de tous les lots joues
en un seul rapport HTML browsable (logs + captures), via `rebot`.

La matrice (DB) reste la source de verite de la COUVERTURE. Ce rapport est
l'artefact d'execution : il montre TOUTES les executions de la campagne (un rejeu
apparait donc comme un run distinct). On combine (pas `--merge`) pour rester
robuste quel que soit le nombre de cibles/lots.
"""

import subprocess
import sys
from pathlib import Path

from core.paths import paths
from services.campaigns.db import get_connection
from services.campaigns.manager import get_campaign


def _batch_outputs(campaign_id):
    """output.xml de chaque lot de la campagne (ordre chronologique via le nom de dossier)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT report_path FROM campaign_cells "
            "WHERE campaign_id = ? AND report_path IS NOT NULL AND report_path != '' "
            "ORDER BY report_path", (campaign_id,)).fetchall()
    outputs = []
    for r in rows:
        folder = Path(r["report_path"])
        candidates = (
            folder / "Output_merge" / "output_merge.xml",
            folder / "Output_original" / "output_original.xml",
            folder / "output.xml",
        )
        for candidate in candidates:
            if candidate.exists():
                outputs.append(str(candidate))
                break
    return outputs


def build_campaign_report(campaign_id):
    """Genere le rapport consolide de tous les lots. None si rien a agreger."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        return None
    outputs = _batch_outputs(campaign_id)
    if not outputs:
        return None

    out_dir = paths.get_campaign_report_folder(campaign_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = campaign.get("name", campaign_id)

    # rebot renvoie le NOMBRE de tests en echec comme code de sortie : on ne peut
    # pas s'y fier. On valide la generation par la presence de report.html.
    subprocess.run([
        sys.executable, "-m", "robot.rebot",
        "-N", f"Campagne - {name}",
        "-d", str(out_dir),
        "-o", "output.xml",
        "-r", "report.html",
        "-l", "log.html",
        *outputs,
    ], check=False)

    if not (out_dir / "report.html").exists():
        return None
    return {"report_dir": str(out_dir), "report": "report.html",
            "log": "log.html", "sources": len(outputs)}
