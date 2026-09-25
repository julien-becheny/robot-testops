"""
Profils de charge : SOURCE DE VÉRITÉ unique des types de test.

- TestOps (UI) lit `list_test_types()` pour afficher dynamiquement les bons
  champs (avec défauts) selon le type choisi.
- Le moteur d'exécution utilise `validate_params()` pour valider/convertir les
  paramètres saisis ; le profil de charge lui-même est construit par le locustfile
  (modèle fermé) ou par le scénario k6 (modèle ouvert).

Ajouter/ajuster un type ou un défaut se fait ICI, à un seul endroit : l'UI
(dynamique) n'a pas à changer.

**Chaque type déclare son modèle de charge**, et le modèle détermine le moteur.
Voir la règle `LOAD_CLOSED` dans docs/regles_apprises.md et
docs/modeles_de_charge.md pour le critère de choix.

Chaque champ : name, label, type (duration|int|float), default [, min, max].
"""

import re

_DURATION_RE = re.compile(r'^(\d+(ms|s|m|h))+$')

# Les deux façons de produire de la charge. L'utilisateur choisit l'INTENTION ;
# le moteur en découle (Locust ne sait pas tenir un débit, k6 si).
MODELS = {
    "closed": {
        "label": "Des utilisateurs qui travaillent",
        "hint": "Tu fixes un NOMBRE d'utilisateurs. Chacun attend sa réponse avant de "
                "repartir : si l'appli ralentit, la charge produite baisse d'elle-même. "
                "C'est le comportement d'agents devant leur écran.",
        "engine": "locust",
    },
    "open": {
        "label": "Un flux qui arrive",
        "hint": "Tu fixes un DÉBIT (requêtes par seconde), tenu quoi qu'il arrive. C'est le "
                "comportement d'une synchronisation planifiée, d'un pic de connexion ou "
                "d'un autre système qui appelle. Seul ce modèle montre l'engorgement.",
        "engine": "k6",
    },
}


# Champs avancés communs (think time + seuils de réussite).
# Think time à 1 s : un utilisateur métier enchaîne rarement plus vite, et une
# valeur basse fait surtout travailler l'injecteur (mesures faussées).
_PROCESSES = {"name": "processes", "label": "Processus d'injection", "type": "int",
              "default": 1, "min": 1, "max": 64}

# Seuil de queue. Sans lui, le p95 laisse 5 % des requêtes libres de durer n'importe
# combien de temps - or ce sont celles dont les utilisateurs parlent. Le rapport 2
# au p95 vient de l'exemple du SRE Workbook ; un objectif négocié le remplace.
_P99 = {"name": "p99_ms", "label": "Seuil p99 (ms)", "type": "int",
        "default": 1600, "min": 1, "max": 120000}

_ADVANCED = [
    {"name": "think_time", "label": "Think time (s)", "type": "float",
     "default": 1.0, "min": 0, "max": 60},
    {"name": "p95_ms", "label": "Seuil p95 (ms)", "type": "int",
     "default": 800, "min": 1, "max": 120000},
    _P99,
    {"name": "error_pct", "label": "Seuil erreurs (%)", "type": "float",
     "default": 1, "min": 0, "max": 100},
    _PROCESSES,
]

# Modèle ouvert : pas de think time (le débit est imposé, pas déduit du rythme des
# utilisateurs) ni de multi-processus (k6 exploite tous les coeurs d'un seul process).
# `max_vus` est le plafond de front de mer que k6 s'autorise pour tenir le débit.
_ADVANCED_OPEN = [
    {"name": "p95_ms", "label": "Seuil p95 (ms)", "type": "int",
     "default": 800, "min": 1, "max": 120000},
    _P99,
    {"name": "error_pct", "label": "Seuil erreurs (%)", "type": "float",
     "default": 1, "min": 0, "max": 100},
    {"name": "max_vus", "label": "VUs max autorisés", "type": "int",
     "default": 400, "min": 1, "max": 20000},
]

PROFILES = {
    "smoke": {
        "label": "Smoke - vérification rapide",
        "model": "closed",
        "description": "Vérifie que l'appli répond (1 utilisateur, très court). À lancer en premier.",
        "goal": "Vérifier que l'appli répond correctement avant tout test de charge.",
        "watch": "La réussite des requêtes : aucune erreur attendue (réponse binaire OK/KO).",
        "fields": [
            {"name": "duration", "label": "Durée", "type": "duration", "default": "10s"},
        ],
        "advanced": [],
    },
    "load": {
        "label": "Load - charge nominale",
        "model": "closed",
        "description": "Reproduit la charge normale attendue : montée, palier, descente. Le test de référence.",
        "goal": "Valider que le système tient la charge nominale attendue en production.",
        "watch": "Le p95 doit rester sous le seuil et le taux d'erreur proche de zéro. "
                 "Surveille aussi le débit produit : s'il décroche, la charge s'est "
                 "auto-limitée et le p95 affiché est optimiste.",
        "fields": [
            {"name": "vus", "label": "VUs cibles", "type": "int", "default": 200, "min": 1, "max": 2000},
            {"name": "ramp_up", "label": "Montée", "type": "duration", "default": "1m30s"},
            {"name": "steady", "label": "Palier", "type": "duration", "default": "1m30s"},
            {"name": "ramp_down", "label": "Descente", "type": "duration", "default": "30s"},
        ],
        "advanced": _ADVANCED,
    },
    "stress": {
        "label": "Stress - point de rupture",
        "model": "closed",
        "description": "Pousse au-delà du nominal pour trouver le point de rupture du système.",
        "goal": "Trouver le point de rupture en poussant au-delà de la charge nominale.",
        "watch": "À quel palier le p95 explose et les erreurs montent, puis si le système "
                 "récupère à la descente. Le débit plafonne avant : c'est le premier signe.",
        "fields": [
            {"name": "vus", "label": "VUs au pic", "type": "int", "default": 200, "min": 1, "max": 5000},
            {"name": "ramp_up", "label": "Montée vers le pic", "type": "duration", "default": "1m"},
            {"name": "peak_hold", "label": "Maintien au pic", "type": "duration", "default": "30s"},
            {"name": "ramp_down", "label": "Descente", "type": "duration", "default": "20s"},
        ],
        "advanced": [
            {**f, "default": 1500} if f["name"] == "p95_ms"
            else {**f, "default": 3000} if f["name"] == "p99_ms"
            else {**f, "default": 5} if f["name"] == "error_pct"
            else f
            for f in _ADVANCED
        ],
    },
    "endurance": {
        "label": "Endurance - tenue dans le temps (fuites mémoire)",
        "model": "closed",
        "description": "Charge modérée mais longue : révèle les fuites mémoire et la dégradation dans le temps.",
        "goal": "Détecter les fuites mémoire et la dégradation lente sur une longue durée.",
        "watch": "La dérive progressive du p95 et de la mémoire serveur (pas un pic ponctuel). "
                 "Un débit qui s'effrite sans erreur trahit le même ralentissement.",
        "fields": [
            {"name": "vus", "label": "VUs", "type": "int", "default": 30, "min": 1, "max": 2000},
            {"name": "duration", "label": "Durée", "type": "duration", "default": "30m"},
        ],
        "advanced": _ADVANCED,
    },
    "capacity": {
        "label": "Capacité - paliers (staircase)",
        "model": "closed",
        "description": "Monte par paliers successifs jusqu'à trouver le nombre de VUs où le p95 décroche.",
        "goal": "Mesurer la capacité maximale : à partir de combien de VUs le système se dégrade.",
        "watch": "Le palier où le p95 franchit le seuil (le test s'arrête là) et où le débit "
                 "plafonne : au-delà, les VUs supplémentaires n'ajoutent plus de charge.",
        "fields": [
            {"name": "vus_start", "label": "VUs de départ", "type": "int", "default": 100, "min": 1, "max": 5000},
            {"name": "vus_max", "label": "VUs max", "type": "int", "default": 600, "min": 1, "max": 10000},
            {"name": "vus_step", "label": "Pas (incrément)", "type": "int", "default": 100, "min": 1, "max": 5000},
            {"name": "ramp", "label": "Montée entre paliers", "type": "duration", "default": "30s"},
            {"name": "steady", "label": "Durée d'un palier", "type": "duration", "default": "2m"},
        ],
        "advanced": _ADVANCED,
    },
    "calibration": {
        "label": "Calibrage - capacité de l'injecteur",
        "model": "closed",
        "description": "Mesure ce que CETTE machine sait produire avant de saturer. À lancer avant "
                       "toute campagne : un injecteur saturé fausse toutes les mesures.",
        "goal": "Connaître le débit maximal que l'injecteur peut générer sur ce scénario.",
        "watch": "Le débit atteint quand le CPU franchit le seuil. Prévois un facteur 3 de marge "
                 "entre ce débit et celui de tes tests. Attention : si la cible cède avant "
                 "l'injecteur, le chiffre mesure la cible, pas la machine.",
        "fields": [
            {"name": "vus_start", "label": "VUs de départ", "type": "int", "default": 50, "min": 1, "max": 5000},
            {"name": "vus_max", "label": "VUs max", "type": "int", "default": 500, "min": 1, "max": 10000},
            {"name": "vus_step", "label": "Pas (incrément)", "type": "int", "default": 50, "min": 1, "max": 5000},
            {"name": "ramp", "label": "Montée entre paliers", "type": "duration", "default": "10s"},
            {"name": "steady", "label": "Durée d'un palier", "type": "duration", "default": "20s"},
        ],
        # Think time nul : on cherche à saturer l'injecteur, pas à imiter un utilisateur.
        "advanced": [
            {"name": "think_time", "label": "Think time (s)", "type": "float",
             "default": 0, "min": 0, "max": 60},
            {"name": "cpu_max_pct", "label": "Seuil CPU injecteur (%)", "type": "int",
             "default": 85, "min": 10, "max": 100},
            _PROCESSES,
        ],
    },
    "open_load": {
        "label": "Débit nominal - flux imposé",
        "model": "open",
        "description": "Envoie un débit constant de requêtes, tenu même si le système ralentit. "
                       "À utiliser quand la charge ne vient pas d'utilisateurs devant leur "
                       "écran : synchronisation, pic de connexion, autre système qui appelle.",
        "goal": "Vérifier que le système absorbe un débit d'arrivée donné sans s'engorger.",
        "watch": "Le p95, et surtout les requêtes que k6 n'a PAS pu lancer : dès que le débit "
                 "demandé n'est plus tenu, la file s'allonge - premier signe d'engorgement.",
        "fields": [
            {"name": "rate", "label": "Débit cible (req/s)", "type": "int",
             "default": 100, "min": 1, "max": 100000},
            {"name": "ramp_up", "label": "Montée", "type": "duration", "default": "30s"},
            {"name": "steady", "label": "Palier", "type": "duration", "default": "1m30s"},
            {"name": "ramp_down", "label": "Descente", "type": "duration", "default": "20s"},
        ],
        "advanced": _ADVANCED_OPEN,
    },
    "open_stress": {
        "label": "Stress à débit - au-delà du nominal",
        "model": "open",
        "description": "Pousse le débit d'arrivée bien au-delà du nominal : montre à partir de "
                       "quel rythme le système accumule du retard, et s'il s'en remet ensuite.",
        "goal": "Voir ce qui se passe quand il arrive plus de requêtes que le système n'en "
                "traite : engorgement progressif ou effondrement.",
        "watch": "Le moment où les requêtes cessent de partir, la vitesse à laquelle le p95 "
                 "s'envole, et si le système se rétablit pendant la descente.",
        "fields": [
            {"name": "rate", "label": "Débit au pic (req/s)", "type": "int",
             "default": 300, "min": 1, "max": 100000},
            {"name": "ramp_up", "label": "Montée vers le pic", "type": "duration",
             "default": "1m"},
            {"name": "peak_hold", "label": "Maintien au pic", "type": "duration",
             "default": "30s"},
            {"name": "ramp_down", "label": "Descente", "type": "duration", "default": "20s"},
        ],
        "advanced": [
            {**f, "default": 1500} if f["name"] == "p95_ms"
            else {**f, "default": 3000} if f["name"] == "p99_ms"
            else {**f, "default": 5} if f["name"] == "error_pct"
            else f
            for f in _ADVANCED_OPEN
        ],
    },
    "open_endurance": {
        "label": "Endurance à débit - tenue dans le temps",
        "model": "open",
        "description": "Maintient un débit modéré très longtemps : révèle les fuites mémoire et "
                       "la dégradation lente, sans jamais lever le pied si le système ralentit.",
        "goal": "Détecter une dérive lente sous un flux d'arrivée constant et réaliste.",
        "watch": "La dérive du p95 entre le début et la fin, et l'apparition tardive de "
                 "requêtes non parties : le signe que le retard s'accumule.",
        "fields": [
            {"name": "rate", "label": "Débit (req/s)", "type": "int",
             "default": 50, "min": 1, "max": 100000},
            {"name": "duration", "label": "Durée", "type": "duration", "default": "30m"},
        ],
        "advanced": _ADVANCED_OPEN,
    },
    "open_capacity": {
        "label": "Capacité en débit - paliers",
        "model": "open",
        "description": "Monte le débit par paliers jusqu'à ce que le système décroche. Le test "
                       "s'arrête au décrochage et annonce le débit réellement absorbé.",
        "goal": "Mesurer combien de requêtes par seconde le système absorbe réellement.",
        "watch": "Le palier où les requêtes commencent à ne plus partir : c'est la capacité "
                 "d'absorption, exprimée en débit et non en nombre d'utilisateurs.",
        "fields": [
            {"name": "rate_start", "label": "Débit de départ (req/s)", "type": "int",
             "default": 50, "min": 1, "max": 100000},
            {"name": "rate_max", "label": "Débit max (req/s)", "type": "int",
             "default": 500, "min": 1, "max": 100000},
            {"name": "rate_step", "label": "Pas (incrément)", "type": "int",
             "default": 50, "min": 1, "max": 100000},
            {"name": "ramp", "label": "Montée entre paliers", "type": "duration",
             "default": "10s"},
            {"name": "steady", "label": "Durée d'un palier", "type": "duration",
             "default": "30s"},
        ],
        "advanced": _ADVANCED_OPEN,
    },
}


def list_test_types():
    """Définitions pour l'UI : champs (base + avancés) et défauts, par type."""
    return [
        {"id": tid, "label": p["label"], "description": p["description"],
         "model": p["model"], "engine": MODELS[p["model"]]["engine"],
         "goal": p["goal"], "watch": p["watch"],
         "fields": p["fields"], "advanced": p["advanced"]}
        for tid, p in PROFILES.items()
    ]


def list_models():
    """Familles de charge (libellé + explication) pour regrouper les types dans l'UI."""
    return [{"id": mid, **model} for mid, model in MODELS.items()]


def engine_for(test_type):
    """Moteur d'injection imposé par le modèle de charge de ce type."""
    if test_type not in PROFILES:
        raise ValueError(f"Type de test inconnu : {test_type}")
    return MODELS[PROFILES[test_type]["model"]]["engine"]


def _all_fields(test_type):
    p = PROFILES[test_type]
    return p["fields"] + p["advanced"]


def validate_params(test_type, raw):
    """Valide/convertit les params reçus selon les specs du type. Lève ValueError."""
    if test_type not in PROFILES:
        raise ValueError(f"Type de test inconnu : {test_type}")
    raw = raw or {}
    return {f["name"]: _coerce(f, raw.get(f["name"], f["default"]))
            for f in _all_fields(test_type)}


def _coerce(field, value):
    kind = field["type"]
    if kind == "duration":
        s = str(value)
        if not _DURATION_RE.match(s):
            raise ValueError(f"Durée invalide pour « {field['label']} » : {value}")
        return s
    if kind == "int":
        return _clamp(int(value), field)
    if kind == "float":
        return _clamp(float(value), field)
    raise ValueError(f"Type de champ inconnu : {kind}")


def _clamp(value, field):
    if "min" in field:
        value = max(field["min"], value)
    if "max" in field:
        value = min(field["max"], value)
    return value
