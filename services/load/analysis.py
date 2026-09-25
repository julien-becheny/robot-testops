"""
Analyse déterministe des résultats de charge (moteur de règles, PAS d'IA).

Le domaine est borné et la fiabilité prime : chaque règle produit un « finding »
(constat) explicable et reproductible. Une règle = une fonction (result, params,
test_type) -> finding | None. L'ordre d'affichage va du plus critique au plus
informatif.

Un finding = {"level": crit|warn|info|good, "title": str, "detail": str}.
"""

_ORDER = {"crit": 0, "warn": 1, "info": 2, "good": 3}


def analyze(result: dict, params: dict, test_type: str) -> list:
    """Applique toutes les règles et renvoie les findings triés par sévérité."""
    if not result or result.get("error"):
        return []
    params = params or {}
    findings = []
    for rule in _rules_for(result, test_type):
        finding = rule(result, params, test_type)
        if finding:
            findings.append(finding)
    findings.sort(key=lambda f: _ORDER.get(f["level"], 9))
    return findings


def _rules_for(result: dict, test_type: str) -> list:
    """Choisit le jeu de règles : les signaux dépendent du modèle de charge.

    Le calibrage cherche VOLONTAIREMENT la saturation de l'injecteur, et le modèle
    ouvert n'a ni utilisateurs à compter ni auto-limitation à débusquer : les règles
    du modèle fermé y seraient au mieux muettes, au pire trompeuses.
    """
    if test_type == "calibration":
        return _CALIBRATION_RULES
    if result.get("model") == "open":
        return _OPEN_RULES
    return _RULES


def compute_status(result: dict, params: dict) -> str:
    """Verdict global du run : « ok », « warn » ou « fail ».

    « Seuils tenus » ne suffit pas : un smoke n'a AUCUN seuil et paraîtrait vert
    même avec 75 % d'erreurs. On combine donc trois signaux :
      - un seuil explicite non tenu -> fail ;
      - des erreurs NON encadrées par un seuil d'erreur (ex smoke) -> fail/warn ;
      - des checks en échec NON expliqués par les erreurs HTTP (bug fonctionnel).
    """
    if not result or result.get("error"):
        return "fail"
    params = params or {}
    if result.get("test_type") == "calibration":
        # Saturer l'injecteur est l'objectif : seules les erreurs HTTP dégradent le verdict.
        if _mass_failure(result) is not None:
            return "fail"
        err = _num(result.get("error_rate")) or 0
        return "warn" if err > 0 else "ok"
    if not result.get("thresholds_ok", True):
        return "fail"
    err = result.get("error_rate")
    if "error_pct" not in params and isinstance(err, (int, float)) and err > 0:
        return "fail" if err >= 0.01 else "warn"
    checks = result.get("checks_rate")
    if isinstance(checks, (int, float)) and checks < 1:
        base_err = err if isinstance(err, (int, float)) else 0
        # Arrondi : évite qu'un bruit flottant (ex 0.03 - 0.03 = 2.7e-17) déclenche « warn ».
        unexplained = round((1 - checks) - base_err, 4)
        if unexplained >= 0.01:
            return "fail"
        if unexplained > 0:
            return "warn"
    if _injector_saturated(result) or _load_not_applied(result) or _load_self_limited(result):
        return "warn"  # rien ne s'est mal passé, mais la mesure n'est pas concluante
    if _load_not_delivered(result):
        return "warn"  # le débit demandé n'a pas été tenu : le système n'absorbe pas tout
    return "ok"


def _f(level: str, title: str, detail: str) -> dict:
    return {"level": level, "title": title, "detail": detail}


def _num(value):
    return value if isinstance(value, (int, float)) else None


CPU_WARN_PCT = 90
CPU_TIGHT_PCT = 75
VUS_DEFICIT_PCT = 5
THROUGHPUT_SHORTFALL_PCT = 20
# Modèle ouvert : part des itérations que k6 n'a pas pu lancer à l'heure dite.
DROPPED_PCT = 1
# Stress et capacité cherchent à dépasser le plafond : l'auto-limitation y est un
# symptôme attendu, pas un verdict faussé.
_SELF_LIMIT_WARN_TYPES = ("load", "endurance")


def _injector_saturated(result: dict) -> bool:
    """L'injecteur a-t-il saturé ? Si oui, les temps mesurés ne décrivent plus le serveur."""
    if result.get("injector_cpu_warning"):
        return True
    cpu = _num(result.get("injector_cpu_max"))
    return cpu is not None and cpu >= CPU_WARN_PCT


def _load_not_applied(result: dict) -> bool:
    """La charge réellement appliquée est-elle en dessous de celle demandée ?"""
    deficit = _num(result.get("vus_deficit_pct"))
    return deficit is not None and deficit >= VUS_DEFICIT_PCT


def _load_self_limited(result: dict) -> bool:
    """L'auto-limitation rend-elle le verdict optimiste ?

    Voir `_rule_throughput_shortfall` : le modèle fermé fait retomber le débit produit
    quand le serveur ralentit. Sur un stress ou une capacité, c'est le résultat cherché.
    """
    shortfall = _num(result.get("throughput_shortfall_pct"))
    if shortfall is None or shortfall < THROUGHPUT_SHORTFALL_PCT:
        return False
    return result.get("test_type") in _SELF_LIMIT_WARN_TYPES


def _load_not_delivered(result: dict) -> bool:
    """Modèle ouvert : le débit demandé n'a pas été envoyé en entier."""
    dropped = _num(result.get("dropped_pct"))
    return dropped is not None and dropped >= DROPPED_PCT


def _floor_ratio(result: dict):
    """Part du p95 déjà consommée par la requête la plus rapide (plancher)."""
    p95 = _num(result.get("p95_ms"))
    floor = _num(result.get("min_ms"))
    if p95 is None or floor is None or p95 <= 0:
        return None
    return floor / p95


# ===== RÈGLES =====

def _rule_injector(result, params, test_type):
    """La machine qui GÉNÈRE la charge a saturé : le run ne mesure plus le serveur."""
    cpu = _num(result.get("injector_cpu_max"))
    if not _injector_saturated(result):
        if cpu is not None and cpu >= CPU_TIGHT_PCT:
            return _f("warn", f"Marge faible sur l'injecteur (CPU max ~ {cpu:.0f} %)",
                      "La machine de test approche de sa limite (alerte à 90 %). Les mesures "
                      "restent exploitables, mais une charge un peu plus forte les fausserait. "
                      "Ne pousse pas les VUs sans surveiller cette valeur.")
        return None
    mesure = f" (CPU max ~ {cpu:.0f} %)" if cpu else ""
    return _f("crit", f"Mesure non fiable : injecteur saturé{mesure}",
              "La machine de test a dépassé 90 % de CPU : l'injecteur ne traite plus les "
              "réponses assez vite et cette attente s'ajoute aux temps mesurés. Les latences "
              "(et le plafond de débit) décrivent alors ta machine, pas le serveur. Baisse la "
              "charge, mets un think time réaliste, ou répartis l'injection - côté Locust sur "
              "plusieurs coeurs (--processes, indisponible sous Windows), sinon sur plusieurs "
              "machines.")


def _rule_vus_deficit(result, params, test_type):
    """Moins d'utilisateurs virtuels actifs que le plan ne le demandait."""
    if not _load_not_applied(result):
        return None
    deficit = _num(result.get("vus_deficit_pct"))
    reel = _num(result.get("vus_max"))
    vise = _num(result.get("vus_target_max"))
    chiffres = f" ({int(reel)} atteints sur {int(vise)} visés)" if reel and vise else ""
    return _f("warn", f"Charge appliquée inférieure à la charge demandée : -{deficit:.0f} %",
              f"Le plan n'a pas été tenu{chiffres} : l'injecteur n'a pas lancé tous les "
              "utilisateurs prévus, palier déjà stabilisé. Le verdict porte donc sur une "
              "charge plus faible qu'annoncé. Cause habituelle : injecteur à bout de souffle.")


def _rule_throughput_shortfall(result, params, test_type):
    """Modèle fermé : le ralentissement du serveur a réduit la charge produite."""
    shortfall = _num(result.get("throughput_shortfall_pct"))
    if shortfall is None or shortfall < THROUGHPUT_SHORTFALL_PCT:
        return None
    actual = _num(result.get("throughput_actual_rps"))
    nominal = _num(result.get("throughput_nominal_rps"))
    users = _num(result.get("throughput_users"))
    chiffres = (f" ({actual:.0f} req/s produits contre {nominal:.0f} attendus à "
                f"{int(users)} utilisateurs)") if actual and nominal and users else ""
    if test_type in ("stress", "capacity"):
        return _f("info", f"Charge auto-limitée : -{shortfall:.0f} % de débit{chiffres}",
                  "Le débit produit a décroché : chaque utilisateur virtuel attend sa réponse "
                  "avant de repartir, donc l'injecteur ralentit avec le serveur. C'est le "
                  "signe que le plafond est atteint - mais la dégradation réelle est PIRE "
                  "que ce que montre le p95 : de vrais utilisateurs auraient continué "
                  "d'arriver au même rythme.")
    return _f("warn", f"Charge auto-limitée : -{shortfall:.0f} % de débit{chiffres}",
              "Chaque utilisateur virtuel attend sa réponse avant de repartir : quand le "
              "serveur ralentit, l'injecteur ralentit avec lui et cesse d'appliquer la charge "
              "prévue. De vrais utilisateurs, eux, continueraient d'arriver : la file "
              "s'allongerait et les temps de réponse seraient bien pires. Le p95 de ce run "
              "est donc optimiste - traite-le comme un plancher, pas comme une mesure.")


def _rule_dropped(result, params, test_type):
    """Modèle ouvert : k6 n'a pas réussi à envoyer tout le débit demandé."""
    if not _load_not_delivered(result):
        return None
    if test_type == "open_capacity" and result.get("breach"):
        return None  # le décrochage est le résultat cherché : `_rule_open_capacity` le dit
    pct = _num(result.get("dropped_pct")) or 0
    dropped = int(_num(result.get("dropped_iterations")) or 0)
    cible = _num(result.get("rate_target"))
    obtenu = _num(result.get("reqs_per_sec"))
    plafond = _num(result.get("max_vus_allowed"))
    atteints = _num(result.get("vus_max"))
    debits = (f" Débit demandé {cible:.0f} req/s, débit réel {obtenu:.0f} req/s."
              if cible and obtenu else "")
    if plafond and atteints and atteints >= plafond:
        cause = (f" Le plafond de {int(plafond)} VUs a été atteint : chaque requête occupe "
                 "un VU jusqu'à sa réponse, donc un système lent les consomme tous. "
                 "Relance en augmentant « VUs max autorisés » pour distinguer l'engorgement "
                 "du système de la limite que tu as posée.")
    elif _injector_saturated(result):
        cause = (" Les VUs disponibles n'ont pourtant pas été tous consommés, et la machine "
                 "de test a saturé : le retard vient sans doute de l'injecteur, pas du "
                 "système testé. Refais le run sur une machine moins chargée avant de "
                 "conclure.")
    else:
        cause = (" Les VUs disponibles restent occupés à attendre les réponses : c'est le "
                 "système testé qui ne suit pas le rythme d'arrivée.")
    return _f("crit", f"Débit non tenu : {pct:.1f} % des requêtes n'ont pas pu partir",
              f"{dropped} requête(s) prévue(s) n'ont jamais été envoyées.{debits}{cause} "
              "En production, ces requêtes ne disparaîtraient pas : elles s'accumuleraient "
              "en file d'attente, et les temps de réponse seraient encore pires.")


def _rule_open_delivered(result, params, test_type):
    """Modèle ouvert : le débit demandé a bien été appliqué (mesure non auto-limitée)."""
    if _load_not_delivered(result) or result.get("dropped_pct") is None:
        return None
    if test_type == "open_capacity":
        return None  # `_rule_open_capacity` porte déjà le verdict de ce type
    cible = _num(result.get("rate_target"))
    if not cible:
        return None
    return _f("good", f"Débit tenu : {cible:.0f} req/s réellement envoyées",
              "Toutes les requêtes prévues sont parties à l'heure dite, quelle que soit la "
              "vitesse du système. Les temps de réponse mesurés ici ne sont pas optimistes : "
              "ils décrivent le service sous la charge annoncée.")


def _rule_open_next_step(result, params, test_type):
    """Verdict global et suite à donner, pour un test à débit imposé."""
    if _load_not_delivered(result) or not result.get("thresholds_ok"):
        return None
    if (_num(result.get("error_rate")) or 0) > 0 or test_type == "open_capacity":
        return None
    cible = _num(result.get("rate_target"))
    suite = (f" Monte le débit au-delà de {cible:.0f} req/s pour trouver le point "
             "d'engorgement.") if cible else ""
    return _f("good", "Flux absorbé sans engorgement",
              f"Le système encaisse le débit demandé en tenant ses seuils.{suite}")


def _rule_open_capacity(result, params, test_type):
    """Capacité d'absorption, en débit : le test s'arrête dès que le retard s'installe."""
    if test_type != "open_capacity":
        return None
    breach = result.get("breach") or {}
    if breach.get("cause") == "dropped":
        absorbe = _num(breach.get("rps")) or 0
        return _f("crit", f"Capacité d'absorption : ~{absorbe:.0f} req/s",
                  f"À {_num(breach.get('t')) or 0:.0f} s, des requêtes ont cessé de partir sur "
                  "deux relévés d'affilée : le rythme d'arrivée dépasse ce que le système "
                  f"traite. Au-delà de ~{absorbe:.0f} req/s la file s'allonge - c'est ce "
                  "chiffre qu'il faut comparer au trafic attendu en production, pas un "
                  "nombre d'utilisateurs.")
    plafond = _num(result.get("rate_target"))
    if not plafond:
        return None
    return _f("good", f"Capacité non atteinte (absorbé jusqu'à {plafond:.0f} req/s)",
              "Tous les paliers sont passés sans que le retard s'installe. Augmente "
              "« Débit max » pour trouver la vraie limite d'absorption.")


def _rule_local_target(result, params, test_type):
    """Cible hébergée sur la machine qui génère la charge."""
    if not result.get("target_is_local"):
        return None
    return _f("info", "Cible locale : injecteur et serveur partagent la machine",
              "Locust et le système testé se disputent les mêmes coeurs : une partie de la "
              "latence vient de cette concurrence, pas du code testé. Pratique pour apprendre "
              "et comparer avant/après, mais ces chiffres ne sont pas publiables tels quels.")


def _rule_floor(result, params, test_type):
    """Le plancher incompressible domine le temps de réponse."""
    if _mass_failure(result) is not None:
        return None
    ratio = _floor_ratio(result)
    if ratio is None or ratio < 0.7:
        return None
    floor = _num(result.get("min_ms"))
    p95 = _num(result.get("p95_ms"))
    return _f("info", f"Temps dominé par le plancher incompressible ({floor:.0f} ms)",
              f"La requête la plus rapide du run a déjà pris {floor:.0f} ms, soit "
              f"{ratio * 100:.0f} % du p95 ({p95:.0f} ms) : la charge n'ajoute que "
              f"{p95 - floor:.0f} ms. Ce plancher est le trajet réseau plus le traitement au "
              "repos - il ne dit RIEN sur la tenue en charge. Sur une cible distante, c'est "
              "surtout de la distance : compare les runs entre eux, pas à un seuil absolu.")


_MIN_ECHANTILLONS = 100

# Au-delà, les percentiles portent majoritairement sur des échecs : ils mesurent la
# vitesse à laquelle l'erreur revient, pas celle du service.
_ECHEC_MASSIF = 0.5


# Au-delà, l'écart avec la référence n'est plus du bruit de mesure. Deux runs
# identiques sur ce banc se sont tenus à 2 % près.
_DERIVE_PCT = 15


def _rule_baseline(result, params, test_type):
    """Écart avec la référence : c'est ce qui transforme une mesure en surveillance."""
    baseline = result.get("baseline") or {}
    deltas = baseline.get("deltas") or {}
    if not deltas:
        return None
    if not baseline.get("comparable"):
        return _f("info", "Comparaison à la référence impossible : charge différente",
                  "Ce run n'a pas appliqué la même charge que la référence enregistrée. "
                  "Les écarts viendraient de ces réglages, pas du système. Rejouer avec les "
                  "mêmes paramètres, ou redéfinir la référence.")
    # Sur un capacity, le résultat EST le point de rupture. Les percentiles agrègent des
    # paliers différents d'un run à l'autre : les comparer se lit souvent à l'envers.
    capacite = (deltas.get("breach_users") or {}).get("pct")
    debit_rupture = (deltas.get("breach_rps") or {}).get("pct")
    if capacite is not None or debit_rupture is not None:
        gains = [f"{n} {v:+.0f} %" for n, v in
                 (("capacité", capacite), ("débit au plafond", debit_rupture)) if v is not None]
        meilleur = max(v for v in (capacite, debit_rupture) if v is not None)
        if meilleur >= _DERIVE_PCT:
            return _f("good", f"Capacité en hausse ({', '.join(gains)})",
                      "Le système rompt plus tard qu'à la référence, à charge identique. "
                      "Un p95 global en hausse n'est pas contradictoire : le run est monté "
                      "plus haut, donc sa moyenne inclut des paliers que la référence n'a "
                      "jamais atteints.")
        if meilleur <= -_DERIVE_PCT:
            return _f("crit", f"Capacité en baisse ({', '.join(gains)})",
                      "Le système rompt plus tôt qu'à la référence, à charge identique. "
                      "Chercher ce qui a changé : version, volume de données, configuration.")
        return _f("info", f"Capacité stable ({', '.join(gains)})",
                  f"L'écart reste sous {_DERIVE_PCT} %, l'ordre de grandeur du bruit de mesure.")
    p95 = (deltas.get("p95_ms") or {}).get("pct")
    debit = (deltas.get("reqs_per_sec") or {}).get("pct")
    if p95 is None and debit is None:
        return None
    pire = max(v for v in (p95, -debit if debit is not None else None) if v is not None)
    détails = []
    if p95 is not None:
        détails.append(f"p95 {p95:+.0f} %")
    if debit is not None:
        détails.append(f"débit {debit:+.0f} %")
    if pire >= _DERIVE_PCT:
        return _f("crit", f"Régression par rapport à la référence ({', '.join(détails)})",
                  "À charge identique, le système est mesurablement plus lent qu'à la "
                  "référence. Chercher ce qui a changé entre les deux : version applicative, "
                  "volume de données, configuration. Un écart de cette ampleur ne s'explique "
                  "pas par le bruit de mesure.")
    if pire <= -_DERIVE_PCT:
        return _f("good", f"Amélioration par rapport à la référence ({', '.join(détails)})",
                  "À charge identique, le système est mesurablement plus rapide. Si aucune "
                  "optimisation n'a été faite, vérifier que le scénario teste toujours la "
                  "même chose : un gain inexpliqué est aussi suspect qu'une perte.")
    return _f("info", "Conforme à la référence",
              f"Les écarts restent sous {_DERIVE_PCT} %, l'ordre de grandeur du bruit de "
              "mesure entre deux runs identiques. Rien à signaler.")


def _mass_failure(result):
    """Taux d'erreur tel que plus aucun chiffre de performance n'a de sens."""
    rate = _num(result.get("error_rate"))
    return rate if rate is not None and rate >= _ECHEC_MASSIF else None


def _rule_mass_failure(result, params, test_type):
    """Le service n'a pas répondu : tout le reste du rapport est à ignorer."""
    rate = _mass_failure(result)
    if rate is None:
        return None
    return _f("crit", f"Service injoignable ou hors service : {rate * 100:.0f} % d'échecs",
              "Les temps de réponse affichés ne mesurent pas la vitesse du service mais "
              "celle à laquelle les erreurs sont revenues - un refus de connexion est "
              "immédiat, d'où des chiffres flatteurs et trompeurs. Vérifier d'abord que la "
              "cible sélectionnée est la bonne, qu'elle est démarrée et joignable depuis "
              "l'injecteur, avant de tirer la moindre conclusion de performance.")

# Au-delà, le lien devient un facteur de la mesure : les latences incluent de
# l'attente de transmission que rien, côté serveur, ne peut expliquer.
_RESEAU_SATURE_PCT = 70


def _rule_network(result, params, test_type):
    """Le lien réseau approche de sa capacité : il devient le facteur limitant."""
    usage = _num(result.get("network_usage_pct"))
    if usage is None or usage < _RESEAU_SATURE_PCT:
        return None
    speed = _num(result.get("link_speed_mbps"))
    lien = f" du lien à {speed:.0f} Mb/s" if speed else " du lien"
    return _f("warn", f"Réseau proche de la saturation ({usage:.0f} %{lien})",
              "Le trafic occupe une large part de la bande passante disponible : au-delà, "
              "c'est le câble qui plafonne le débit, pas le serveur, et les temps de réponse "
              "incluent de l'attente de transmission. Vérifier la vitesse négociée du lien "
              "(un port retombé à 100 Mb/s sature vers 12 Mo/s), alléger les réponses, ou "
              "injecter depuis un lien plus rapide.")


def _low_sample(result):
    """Nombre de requêtes quand il est trop faible pour des percentiles hauts."""
    total = _num(result.get("reqs_total"))
    if total is None or total >= _MIN_ECHANTILLONS:
        return None
    return int(total)


def _rule_low_sample(result, params, test_type):
    """Trop peu de requêtes pour que p95 et p99 veuillent dire quelque chose."""
    total = _low_sample(result)
    if total is None:
        return None
    rang = max(1, round(total * 0.05))
    pluriel = "s" if rang > 1 else ""
    return _f("info", f"Percentiles peu fiables : {total} requêtes seulement",
              f"Le p95 se lit sur les 5 % les plus lentes, soit {rang} requête{pluriel} ici. "
              "Une seule valeur isolée - pic système, cache froid, résolution de nom - suffit "
              "alors à le fixer, et p95, p99 et max se confondent. Ce n'est pas un défaut du "
              "run : un smoke vérifie que le service répond, il ne mesure pas sa tenue. Les "
              f"percentiles ne deviennent exploitables qu'au-delà de {_MIN_ECHANTILLONS} "
              "requêtes ; juge ici sur le plancher et la médiane.")


def _rule_errors(result, params, test_type):
    """Des requêtes échouent (HTTP)."""
    rate = _num(result.get("error_rate"))
    if rate is None or rate <= 0:
        return None
    pct = rate * 100
    if test_type == "stress" and _mass_failure(result) is None:
        return _f("info", f"{pct:.2f} % de requêtes en erreur",
                  "Des erreurs apparaissent sous la charge : comportement attendu d'un "
                  "stress (on cherche la rupture). Note le palier de VUs où elles démarrent.")
    return _f("crit", f"{pct:.2f} % de requêtes en erreur",
              "Le système rejette des requêtes sous cette charge. À investiguer : "
              "logs serveur, timeouts, saturation du pool de connexions ou de la DB.")


def _rule_checks(result, params, test_type):
    """Validations de contenu (checks) en échec."""
    checks = _num(result.get("checks_rate"))
    if checks is None or checks >= 0.999:
        return None
    err = _num(result.get("error_rate")) or 0
    fail_pct = (1 - checks) * 100
    if err < (1 - checks) - 0.001:
        return _f("crit", f"{fail_pct:.2f} % de validations (checks) en échec",
                  "Des réponses arrivent (HTTP OK) mais leur CONTENU est invalide : "
                  "bug fonctionnel sous charge (réponse tronquée/partielle, mauvaise donnée).")
    return _f("warn", f"{fail_pct:.2f} % de validations (checks) en échec",
              "Des checks échouent, en ligne avec les erreurs HTTP observées.")


def _rule_thresholds(result, params, test_type):
    """Au moins un seuil (threshold k6) n'est pas tenu."""
    if result.get("thresholds_ok"):
        return None
    failed = result.get("failed_thresholds") or []
    detail = ("Seuil(s) non tenu(s) : " + " ; ".join(failed)) if failed \
        else "Au moins un seuil n'est pas tenu."
    return _f("crit", "Seuils non tenus", detail)


def _rule_tail(result, params, test_type):
    """Le p99 face à son seuil : queue de distribution seule, ou service lent partout.

    Les deux diagnostics n'ont pas les mêmes causes : inutile de chercher un
    sous-dimensionnement quand une requête sur cent seulement décroche.
    """
    if _low_sample(result) is not None or _mass_failure(result) is not None:
        return None  # `_rule_low_sample` dit pourquoi ce p99 ne veut rien dire
    p99 = _num(result.get("p99_ms"))
    seuil = _num(params.get("p99_ms")) or _num(result.get("seuil_p99_ms"))
    if p99 is None or not seuil or p99 <= seuil:
        return None
    p95 = _num(result.get("p95_ms"))
    seuil95 = _num(params.get("p95_ms")) or _num(result.get("seuil_p95_ms"))
    if p95 is not None and seuil95 and p95 > seuil95:
        return _f("warn", f"Service lent sur tout le trafic (p95 {p95:.0f} ms, p99 {p99:.0f} ms)",
                  f"Les deux seuils sautent ensemble ({seuil95:.0f} et {seuil:.0f} ms) : ce "
                  "n'est pas une queue de distribution, c'est le service entier qui est "
                  "au-dessus de sa cible. Cherche une cause globale - dimensionnement, "
                  "requête systématiquement lente, saturation - pas un incident ponctuel.")
    courant = f", alors que le p95 tient ({p95:.0f} ms)" if p95 is not None else ""
    return _f("warn", f"Queue de distribution : p99 {p99:.0f} ms > {seuil:.0f} ms",
              f"Une requête sur cent dépasse largement la cible{courant}. C'est la signature "
              "d'un incident intermittent - pause du ramasse-miettes, verrou, cache froid, "
              "requête lente sur un sous-ensemble de données - et non d'un sous-dimensionnement : "
              "ajouter de la ressource n'y changera rien, c'est la cause du pic qu'il faut "
              "trouver. Ce sont pourtant ces 1 % dont les utilisateurs parlent.")


def _rule_ttfb(result, params, test_type):
    """Répartition du temps : traitement serveur (TTFB) vs réseau/transfert."""
    if _low_sample(result) is not None or _mass_failure(result) is not None:
        return None  # p95 et TTFB fixés par les mêmes deux ou trois requêtes
    p95 = _num(result.get("p95_ms"))
    ttfb = _num(result.get("ttfb_p95_ms"))
    if p95 is None or ttfb is None or p95 <= 0:
        return None
    floor = _floor_ratio(result)
    if floor is not None and floor >= 0.7:
        return None  # le TTFB est ici surtout du trajet réseau : `_rule_floor` le dit mieux
    ratio = ttfb / p95
    if ratio >= 0.7:
        return _f("info", f"Temps dominé par le serveur (TTFB ~ {ratio * 100:.0f} % du p95)",
                  "L'essentiel du temps de réponse vient du TRAITEMENT serveur (TTFB), pas "
                  "du réseau. Le goulot est côté backend : requêtes, DB, CPU.")
    if ratio <= 0.4:
        return _f("info", f"Temps dominé par le réseau/transfert (TTFB ~ {ratio * 100:.0f} % du p95)",
                  "Le serveur répond vite (TTFB bas) mais le temps total est élevé : le temps "
                  "part dans le réseau ou le transfert (payload volumineux).")
    return None


def _rule_margin(result, params, test_type):
    """Marge du p95 par rapport à son seuil (si les seuils sont tenus)."""
    if not result.get("thresholds_ok") or _mass_failure(result) is not None:
        return None
    p95 = _num(result.get("p95_ms"))
    seuil = _num(params.get("p95_ms"))
    if p95 is None or seuil is None or seuil <= 0:
        return None
    ratio = p95 / seuil
    if ratio >= 0.85:
        return _f("warn", f"Marge faible sous le seuil p95 ({p95:.0f} / {seuil:.0f} ms)",
                  "Le p95 tient mais frôle le seuil : peu de réserve avant dépassement.")
    if ratio <= 0.5 and test_type in ("load", "smoke") and not _load_self_limited(result):
        return _f("good", f"Large marge sous le seuil p95 ({p95:.0f} / {seuil:.0f} ms)",
                  "Beaucoup de réserve. Tu peux pousser plus fort (VUs plus élevés) ou lancer "
                  "un stress pour trouver la limite.")
    return None


def _rule_capacity(result, params, test_type):
    """Capacité (staircase) : verdict quand AUCUNE rupture p95 n'a été détectée
    (le cas avec rupture est traité par `_rule_breach`)."""
    if test_type != "capacity" or result.get("breach"):
        return None
    if _mass_failure(result) is not None:
        return None
    vmax = _num(result.get("vus_max"))
    label = f"{int(vmax)} VUs" if vmax else "?"
    if _injector_saturated(result) or _load_not_applied(result):
        return _f("warn", f"Capacité non concluante (tenu jusqu'à {label}, mesure faussée)",
                  "Le serveur n'a pas rompu, mais la charge annoncée n'a pas été appliquée "
                  "correctement (injecteur saturé ou utilisateurs manquants) : le plafond "
                  "observé peut être celui de la machine de test. Refais le run avant de "
                  "conclure sur la capacité.")
    if result.get("thresholds_ok"):
        return _f("good", f"Capacité non atteinte (tenu jusqu'à {label})",
                  "Le système a tenu toute la montée sans que le p95 ne franchisse le seuil. "
                  "Augmente « VUs max » pour trouver la vraie limite.")
    return _f("info", f"Capacité limitée vers ~{label}",
              "Pas de rupture p95, mais le run n'est pas au vert (erreurs ou p99 hors seuil). "
              "Regarde le taux d'erreur, la queue de distribution et la timeline pour situer "
              "la dégradation.")


def _rule_breach(result, params, test_type):
    """Point de rupture (Locust) : conditions EXACTES au moment où le p95 a cédé."""
    breach = result.get("breach")
    if not breach or _mass_failure(result) is not None:
        return None
    seuil = _num(result.get("seuil_p95_ms")) or _num(params.get("p95_ms")) or 0
    reserve = (" Attention : l'injecteur a saturé, cette rupture peut venir de la machine "
               "de test.") if _injector_saturated(result) else ""
    return _f("crit", f"Point de rupture : ~{breach['users']} utilisateurs",
              f"Le p95 a franchi le seuil ({breach['p95_ms']} ms > {int(seuil)} ms) à "
              f"{breach['t']:.0f} s, sous {breach['users']} utilisateurs simultanés "
              f"(débit {breach['rps']:.0f} req/s). C'est ta capacité max estimée : au-delà, "
              f"le service se dégrade sous le seuil.{reserve}")


def _rule_calibration(result, params, test_type):
    """Capacité d'injection de la machine de test, et marge à respecter."""
    debit = _num(result.get("injector_capacity_rps"))
    if debit is None:
        return None
    users = _num(result.get("vus_max")) or 0
    breach = result.get("breach") or {}
    if breach.get("cause") == "cpu":
        marge = debit / 3
        return _f("info", f"Capacité de l'injecteur : ~{debit:.0f} req/s",
                  f"Le CPU a franchi le seuil à {breach.get('cpu', 0):.0f} % sous "
                  f"{int(users)} utilisateurs. Au-delà, cette machine mesure sa propre "
                  f"attente. Garde un facteur 3 de marge : ne planifie pas de test au-delà "
                  f"de ~{marge:.0f} req/s sur ce scénario, ou répartis la charge sur "
                  f"plusieurs coeurs ou plusieurs machines.")
    return _f("good", f"Injecteur non saturé (jusqu'à ~{debit:.0f} req/s)",
              f"Le CPU n'a pas atteint le seuil jusqu'à {int(users)} utilisateurs : cette "
              "machine a encore de la réserve. Augmente « VUs max » pour trouver sa vraie "
              "limite, ou considère ce débit comme suffisant pour tes campagnes.")


def _rule_calibration_target(result, params, test_type):
    """La cible a cédé avant l'injecteur : le chiffre ne mesure alors pas la machine.

    Seules les erreurs HTTP sont discriminantes : une latence qui grimpe accompagne
    aussi la saturation de l'injecteur, qui est ici l'objectif du test.
    """
    rate = _num(result.get("error_rate")) or 0
    if rate <= 0:
        return None
    return _f("warn", f"La cible a cédé avant l'injecteur ({rate * 100:.2f} % d'erreurs)",
              "Des requêtes ont échoué pendant le calibrage : le débit mesuré est celui que "
              "la CIBLE accepte, pas celui que la machine sait produire. Refais le calibrage "
              "sur une cible plus rapide (page statique locale) pour qualifier l'injecteur seul.")


def _rule_next_step(result, params, test_type):
    """Verdict global + prochaine étape suggérée selon le type de test."""
    if (_mass_failure(result) is not None or _injector_saturated(result)
            or _load_not_applied(result) or _load_self_limited(result)):
        return None  # aucune conclusion sur le système tant que la mesure est faussée
    ok = result.get("thresholds_ok")
    err = _num(result.get("error_rate")) or 0
    if test_type == "smoke" and ok and err == 0:
        return _f("good", "Smoke OK",
                  "L'appli répond correctement. Tu peux enchaîner sur un test de charge (load).")
    if test_type == "load" and ok and err == 0:
        return _f("good", "Charge nominale tenue",
                  "Le système encaisse la charge cible. Prochaine étape : un stress (VUs plus "
                  "élevés) pour situer le point de rupture.")
    if test_type == "stress" and not ok:
        return _f("info", "Point de rupture atteint",
                  "Le stress a fait céder au moins un seuil : c'est son but. Note la charge "
                  "(VUs) à laquelle ça bascule = ta capacité max estimée.")
    if test_type == "endurance" and ok and err == 0:
        return _f("good", "Endurance tenue",
                  "Aucune dégradation bloquante sur la durée. Pour traquer une fuite lente, "
                  "compare le p95 de début et de fin dans Grafana.")
    return None


_RULES = [
    _rule_mass_failure,
    _rule_baseline,
    _rule_injector,
    _rule_network,
    _rule_vus_deficit,
    _rule_throughput_shortfall,
    _rule_errors,
    _rule_checks,
    _rule_thresholds,
    _rule_low_sample,
    _rule_tail,
    _rule_floor,
    _rule_ttfb,
    _rule_margin,
    _rule_capacity,
    _rule_breach,
    _rule_local_target,
    _rule_next_step,
]

# Calibrage : on qualifie la MACHINE, pas le système testé.
_CALIBRATION_RULES = [
    _rule_mass_failure,
    _rule_baseline,
    _rule_calibration,
    _rule_calibration_target,
    _rule_local_target,
]

# Modèle ouvert : le débit est imposé, donc ni auto-limitation ni déficit d'utilisateurs
# à surveiller. Le signal propre à ce modèle est ce que l'injecteur n'a PAS pu envoyer.
_OPEN_RULES = [
    _rule_mass_failure,
    _rule_baseline,
    _rule_injector,
    _rule_network,
    _rule_dropped,
    _rule_errors,
    _rule_checks,
    _rule_thresholds,
    _rule_low_sample,
    _rule_tail,
    _rule_floor,
    _rule_ttfb,
    _rule_margin,
    _rule_open_capacity,
    _rule_local_target,
    _rule_open_delivered,
    _rule_open_next_step,
]
