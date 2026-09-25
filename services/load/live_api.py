"""Client HTTP best-effort utilisé par le sous-processus Locust."""

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)


def post_live(
    api_url: str,
    session_id: str,
    route: str,
    payload: dict[str, Any],
) -> bool:
    """Publie une donnée live sans laisser l'API interrompre la charge.

    Args:
        api_url: URL de base de l'API TestOps.
        session_id: Session Socket.IO associée au test de charge.
        route: Route relative à appeler.
        payload: Données JSON métier à transmettre.

    Returns:
        ``True`` si la réponse HTTP est réussie, sinon ``False``.
    """
    try:
        response = requests.post(
            f"{api_url}{route}",
            json={**payload, "session_id": session_id},
            timeout=5,
        )
        response.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.debug("POST best-effort %s non envoyé : %s", route, exc)
        return False