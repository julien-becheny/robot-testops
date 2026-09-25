"""
Liste blanche des cibles de test de charge autorisees.

SECURITE (important) : on ne lance un test de charge QUE sur une cible
declaree ici - soit qu'on possede, soit explicitement prevue pour ca
(cibles de demo publiques). Jamais d'URL arbitraire saisie dans l'UI :
un test de charge sur une cible non autorisee = attaque par deni de service
(DoS), illegal et dangereux.

Le scenario execute pour chaque cible est choisi par le locustfile selon l'id
de la cible (cf. services/load/locustfile_testops.py). Pour ajouter une cible :
declarer une entree ici, puis brancher son scenario dans le locustfile.

FRONTIERE avec config/environments.yaml (decision, pas un oubli) : les deux fichiers
listent des URL, mais ne repondent pas a la meme question. Le referentiel des
environnements dit ou TESTER FONCTIONNELLEMENT ; ce fichier dit ou l'on a le DROIT
d'envoyer de la charge. Les fusionner rendrait tout environnement declare chargeable :
lancer des centaines d'utilisateurs sur un site tiers serait un deni de service.
Un environnement applicatif a charger se declare donc ici, avec son scenario.
"""

LOAD_TARGETS = {
    "quickpizza": {
        "label": "QuickPizza - cible de demo publique",
        "base_url": "https://quickpizza.grafana.com",
        "description": "Cible d'entrainement publique fournie par Grafana.",
    },
}


def get_target(target_id: str):
    """Retourne la config d'une cible autorisee, ou None si inconnue."""
    return LOAD_TARGETS.get(target_id)


def list_targets():
    """Retourne la liste des cibles pour peupler l'UI."""
    return [
        {
            "id": tid,
            "label": t["label"],
            "description": t["description"],
            "base_url": t["base_url"],
        }
        for tid, t in LOAD_TARGETS.items()
    ]
