"""
Locustfile de PRODUCTION pour TestOps (lance en SUBPROCESS par le backend).

Ce fichier ne PRINTE pas : il POSTe vers l'API Flask (comme le listener Robot
Framework du projet), qui repousse en SocketIO vers l'UI React. Tout est recu
par variables d'env :

  TESTOPS_API      : base URL de l'API Flask (POST live / log)
  SESSION_ID       : id de session (room SocketIO)
  TARGET_ID        : id d'une cible de services/load/targets.py -> choisit le scenario
  TEST_TYPE        : smoke | load | stress | endurance | capacity -> choisit la Shape
  PARAMS_JSON      : params valides (JSON) : vus, ramp_up, steady, p95_ms, ...
  STOP_SIGNAL_PATH : fichier dont l'apparition = arret manuel demande
  RESULT_PATH      : ou ecrire le resultat final JSON (lu ensuite par le runner)

Coeur de valeur : un moniteur lit les stats EN DIRECT et, des que le p95 franchit
le seuil de facon soutenue, capture les conditions EXACTES (users, p95, debit,
erreurs) = le POINT DE RUPTURE, puis arrete le test.
"""

import contextlib
import json
import os
import random
import re
import time

import gevent
from locust import HttpUser, LoadTestShape, constant, events, task
from locust.runners import WorkerRunner

from services.load.live_api import post_live

API = os.environ.get("TESTOPS_API", "http://localhost:5001")
SESSION_ID = os.environ.get("SESSION_ID", "")
TARGET_ID = os.environ.get("TARGET_ID", "")
TEST_TYPE = os.environ.get("TEST_TYPE", "load")
PARAMS = json.loads(os.environ.get("PARAMS_JSON", "{}"))
STOP_SIGNAL = os.environ.get("STOP_SIGNAL_PATH", "")
RESULT_PATH = os.environ.get("RESULT_PATH", "")

P95_MS = float(PARAMS.get("p95_ms", 800))
# Seuil de queue : seuls les types qui le declarent l'opposent au run.
P99_MS = float(PARAMS["p99_ms"]) if PARAMS.get("p99_ms") else None
ERROR_PCT = float(PARAMS.get("error_pct", 1))
THINK_TIME = float(PARAMS.get("think_time", 1))
BREACH_HOLD_S = float(os.environ.get("BREACH_HOLD_S", 10))
POLL_S = float(os.environ.get("POLL_S", 2))

# Seuil d'alerte CPU de Locust : au-dela, les reponses attendent dans la boucle
# d'evenements de l'injecteur et ce delai s'ajoute aux temps mesures.
CPU_WARN_PCT = 90
# Calibrage : on cherche VOLONTAIREMENT la saturation de l'injecteur.
CALIBRATION = TEST_TYPE == "calibration"
CPU_MAX_PCT = float(PARAMS.get("cpu_max_pct", 85))

# Le stress cherche le COMPORTEMENT au-dela de la limite : s'arreter au premier
# depassement du seuil le reduirait a un capacity. Le point de rupture est quand
# meme releve, mais la charge continue de monter jusqu'au bout du plan.
STOP_ON_BREACH = TEST_TYPE != "stress"

# Regle LOAD_CLOSED : la charge est pilotee en VUs (modele ferme), donc un serveur
# qui ralentit fait BAISSER le debit produit au lieu d'accumuler du retard. On mesure
# cet ecart la ou il a un sens : charge significative et saturation non voulue.
SHORTFALL_TYPES = {"load", "stress", "endurance", "capacity"}
# Le debit courant de Locust porte sur une fenetre glissante d'environ 10 s : on ne le
# compare qu'apres autant de temps a charge constante, sinon il decrit encore la montee.
STABLE_TICKS = max(1, int(10 / POLL_S))

# Etat partage entre le moniteur (greenlet), la shape et le rapport final.
STATE = {"breach": None, "timeline": [], "t0": None, "stopped": False,
         "cpu_max": 0.0, "cpu_now": 0.0, "cpu_warning": False, "vus_deficit": 0.0,
         "throughput": None}

# Metriques complementaires (parite avec les sorties k6) :
#  - TTFB (temps jusqu'aux headers) via un reservoir pour un p95 representatif ;
#  - checks (validations de contenu) reussis vs total ;
#  - octets ENVOYES (les octets RECUS viennent de stats.total_content_length).
_TTFB_SAMPLES = []
_TTFB_MAX = 5000
_TTFB_SEEN = {"n": 0}
_DATA_SENT = {"bytes": 0}
CHECKS = {"total": 0, "passed": 0}


def _check(ok):
    """Compte une validation de contenu (equivalent d'un « check » k6)."""
    CHECKS["total"] += 1
    if ok:
        CHECKS["passed"] += 1
    return bool(ok)


def _add_ttfb(value):
    """Reservoir sampling : echantillon uniforme borne en memoire."""
    _TTFB_SEEN["n"] += 1
    if len(_TTFB_SAMPLES) < _TTFB_MAX:
        _TTFB_SAMPLES.append(value)
        return
    j = random.randint(0, _TTFB_SEEN["n"] - 1)
    if j < _TTFB_MAX:
        _TTFB_SAMPLES[j] = value


# ===== Multi-processus : les requetes ont lieu dans les workers, le rapport sur le master =====
@events.report_to_master.add_listener
def _report_to_master(client_id, data, **_kwargs):
    """Le worker envoie ses mesures maison au master, puis repart de zero."""
    data["testops"] = {
        "checks": dict(CHECKS),
        "ttfb": list(_TTFB_SAMPLES),
        "data_sent": _DATA_SENT["bytes"],
    }
    CHECKS["total"] = CHECKS["passed"] = 0
    _TTFB_SAMPLES.clear()
    _DATA_SENT["bytes"] = 0


@events.worker_report.add_listener
def _worker_report(client_id, data, **_kwargs):
    """Le master agrege les mesures maison de ses workers."""
    payload = data.get("testops") or {}
    checks = payload.get("checks") or {}
    CHECKS["total"] += checks.get("total", 0)
    CHECKS["passed"] += checks.get("passed", 0)
    for value in payload.get("ttfb") or []:
        _add_ttfb(value)
    _DATA_SENT["bytes"] += payload.get("data_sent", 0)


@events.request.add_listener
def _on_request(response=None, **_kwargs):
    """Capture le TTFB et les octets envoyes pour CHAQUE requete (best-effort)."""
    if response is None:
        return
    with contextlib.suppress(AttributeError, TypeError, ValueError):
        _add_ttfb(response.elapsed.total_seconds() * 1000)
    try:
        body = response.request.body
        if body:
            _DATA_SENT["bytes"] += len(body if isinstance(body, (bytes, bytearray))
                                       else str(body).encode())
    except (AttributeError, TypeError, ValueError, UnicodeEncodeError):
        pass


# ===== Utilitaires =====
_UNIT = {"ms": 0.001, "s": 1, "m": 60, "h": 3600}


def _sec(text, default=0.0):
    """Duree k6-like (« 1m30s », « 45s », « 2m ») -> secondes."""
    if text is None:
        return default
    total, found = 0.0, False
    for num, unit in re.findall(r"(\d+)(ms|s|m|h)", str(text)):
        total += int(num) * _UNIT[unit]
        found = True
    return total if found else default


def _post(route, payload):
    """POST best-effort vers l'API (le live ne doit jamais casser le test)."""
    post_live(API, SESSION_ID, route, payload)


def _log(message):
    _post("/log", {"message": message})


def _sample_cpu(runner):
    """Releve la charge CPU de l'injecteur (machine de test), pas celle du serveur.

    En multi-processus, le master n'injecte pas : c'est le pic des workers qui compte.
    `current_cpu_usage` depuis Locust 2.x, `cpu_usage` sur les versions anterieures.
    """
    workers = getattr(runner, "clients", None)
    if workers:
        usage = max((getattr(w, "cpu_usage", 0) or 0 for w in workers.values()), default=0)
    else:
        usage = getattr(runner, "current_cpu_usage", None)
        if usage is None:
            usage = getattr(runner, "cpu_usage", 0)
    STATE["cpu_now"] = usage or 0
    STATE["cpu_max"] = max(STATE["cpu_max"], usage or 0)
    if getattr(runner, "cpu_warning_emitted", False) or \
            getattr(runner, "worker_cpu_warning_emitted", False):
        STATE["cpu_warning"] = True


# ===== Scenario par cible (une seule classe User, dispatch par TARGET_ID) =====
def _do_root(user):
    with user.client.get("/", name="/", catch_response=True) as r:
        ok = _check(r.status_code == 200)
        if not ok:
            r.failure(f"status {r.status_code}")


_SCENARIO = {
    "quickpizza": _do_root,
}


# HttpUser et non FastHttpUser : `response.elapsed` et `response.request.body` (requests)
# alimentent le TTFB et les octets envoyes, que geventhttpclient n'expose pas. Si l'injecteur
# devient le goulot, la reponse est k6 ou le multi-processus, pas un changement de classe.
class TestOpsUser(HttpUser):
    """Utilisateur virtuel : execute le scenario de la cible choisie."""

    wait_time = constant(THINK_TIME)

    @task
    def run_scenario(self):
        # Pas de repli : il enverrait des requetes hors sujet, sans rien qui en nomme la cause.
        _SCENARIO[TARGET_ID](self)


# ===== Profil de charge (shape) selon le type de test =====
def _build_plan(test_type, p):
    """Segments (t_fin_cumule_s, users_cible, spawn_rate) reproduisant le profil."""
    seg, cursor = [], {"t": 0.0}

    def add(duration, target, spawn):
        if duration <= 0:
            return
        cursor["t"] += duration
        # Plafond a 100/s : Locust deconseille au-dela, et MAINTENIR un palier ne
        # requiert pas un spawn eleve (on n'accelere que pour ATTEINDRE la cible).
        seg.append((cursor["t"], int(target), max(0.1, min(100.0, spawn))))

    if test_type == "smoke":
        add(_sec(p.get("duration", "10s"), 10), 1, 5)
    elif test_type == "endurance":
        v = int(p.get("vus", 30))
        add(_sec(p.get("duration", "30m"), 1800), v, max(1.0, v / 10))
    elif test_type == "load":
        v = int(p.get("vus", 200))
        ru, st, rd = _sec(p.get("ramp_up")), _sec(p.get("steady")), _sec(p.get("ramp_down"))
        add(ru, v, v / ru if ru else v)
        add(st, v, v)
        add(rd, 0, v / rd if rd else v)
    elif test_type == "stress":
        v = int(p.get("vus", 200))
        ru, ph, rd = _sec(p.get("ramp_up")), _sec(p.get("peak_hold")), _sec(p.get("ramp_down"))
        add(ru, v, v / ru if ru else v)
        add(ph, v, v)
        add(rd, 0, v / rd if rd else v)
    elif test_type in ("capacity", "calibration"):
        vs, vm = int(p.get("vus_start", 100)), int(p.get("vus_max", 600))
        step = max(1, int(p.get("vus_step", 100)))
        rmp, std = _sec(p.get("ramp", "30s"), 30), _sec(p.get("steady", "2m"), 120)
        level, n = min(vs, vm), 0
        while level <= vm and n < 40:
            add(rmp, level, max(1.0, step / rmp) if rmp else step)  # montee vers le palier
            add(std, level, level)                                  # palier stable
            level += step
            n += 1
        add(rmp, 0, vm / rmp if rmp else vm)                        # descente finale
    return seg or [(60, int(p.get("vus", 50)), 10)]


_PLAN = _build_plan(TEST_TYPE, PARAMS)


class TestOpsShape(LoadTestShape):
    """Pilote la charge selon le plan. S'arrete a la rupture ou a l'arret manuel."""

    def tick(self):
        if STATE["stopped"] or (STATE["breach"] is not None and STOP_ON_BREACH):
            return None
        t = self.get_run_time()
        for end_s, users, spawn in _PLAN:
            if t < end_s:
                return (users, spawn)
        return None


def _nominal_rps(users, floor_ms):
    """Debit que ces VUs produiraient si le serveur repondait a sa vitesse plancher.

    Loi de Little : debit = utilisateurs / duree d'un cycle, et le cycle le plus court
    possible vaut think time + la requete la plus rapide vue sur ce run.
    """
    if not users or not floor_ms:
        return None
    cycle = THINK_TIME + floor_ms / 1000
    return users / cycle if cycle > 0 else None


def _track_throughput(elapsed, users, rps, stable, floor_ms):
    """Retient le pire ecart entre le debit obtenu et le debit nominal (auto-limitation)."""
    if TEST_TYPE not in SHORTFALL_TYPES or not stable or not rps:
        return
    nominal = _nominal_rps(users, floor_ms)
    if not nominal:
        return
    shortfall = 1 - rps / nominal
    worst = STATE["throughput"]
    if shortfall <= 0 or (worst and shortfall <= worst["shortfall"]):
        return
    STATE["throughput"] = {
        "shortfall": shortfall, "t": round(elapsed, 1), "users": users,
        "rps": round(rps, 1), "nominal_rps": round(nominal, 1),
    }


def _plan_state(elapsed):
    """Users vises par le plan a l'instant t, et si le spawn theorique est termine.

    Tant que le spawn est en cours (montee), un ecart avec les users reels est
    normal : ce n'est qu'apres `users / spawn_rate` qu'il traduit un vrai retard.
    """
    start = 0.0
    for end_s, users, spawn in _PLAN:
        if elapsed < end_s:
            return users, (elapsed - start) >= (users / spawn if spawn else 0)
        start = end_s
    return 0, False


# ===== Cycle de vie : moniteur live + point de rupture + resultat final =====
@events.test_start.add_listener
def _on_start(environment, **_kwargs):
    if isinstance(environment.runner, WorkerRunner):
        return  # le live et le rapport sont pilotes par le master
    environment.stats.use_response_times_cache = True  # alimente le p95 glissant
    STATE["t0"] = time.monotonic()
    gevent.spawn(_monitor, environment)
    _log(f"🚀 Locust - « {TARGET_ID} » - type {TEST_TYPE} (seuil p95 {int(P95_MS)} ms)")


def _monitor(environment):
    """Boucle de surveillance : push live + detection du point de rupture + stop manuel."""
    stats = environment.stats.total
    runner = environment.runner
    breach_since = None
    steady_for, last_users = 0, None
    while not STATE["stopped"]:
        gevent.sleep(POLL_S)
        if STOP_SIGNAL and os.path.exists(STOP_SIGNAL):
            STATE["stopped"] = True
            break
        elapsed = time.monotonic() - STATE["t0"]
        _sample_cpu(runner)
        users = runner.user_count
        steady_for = steady_for + 1 if users == last_users else 0
        last_users = users
        target, settled = _plan_state(elapsed)
        lagging = bool(settled and target and users < target)
        if lagging:
            STATE["vus_deficit"] = max(STATE["vus_deficit"], (target - users) / target)
        p95 = stats.get_current_response_time_percentile(0.95) or 0
        rps = stats.current_rps
        err_rate = stats.fail_ratio
        _track_throughput(elapsed, users, rps, settled and steady_for >= STABLE_TICKS,
                          stats.min_response_time)
        _post("/load-metrics", {"metrics": {
            "vus": users, "vus_target": target or None, "vus_lagging": lagging,
            "cpu": round(STATE["cpu_now"], 1) or None,
            "reqs_per_sec": round(rps, 1),
            "p95_ms": int(p95) if p95 else None, "error_rate": err_rate,
        }})
        STATE["timeline"].append({
            "t": round(elapsed, 1), "users": users, "rps": round(rps, 1),
            "p95_ms": int(p95), "error_rate": round(err_rate, 4),
        })
        if CALIBRATION:
            # Un releve CPU de Locust est deja une moyenne sur 10 s : pas de hold a ajouter.
            if STATE["cpu_now"] >= CPU_MAX_PCT and users > 0:
                STATE["breach"] = {
                    "t": round(elapsed, 1), "users": users, "p95_ms": int(p95),
                    "rps": round(rps, 1), "error_rate": round(err_rate, 4),
                    "cause": "cpu", "cpu": round(STATE["cpu_now"], 1),
                }
                _log(f"🎚️ Injecteur saturé à {STATE['cpu_now']:.0f} % de CPU : "
                     f"~{rps:.0f} req/s avec {users} utilisateurs")
                return
            continue
        if p95 > P95_MS and users > 0:
            breach_since = breach_since or time.monotonic()
            if (STATE["breach"] is None
                    and time.monotonic() - breach_since >= BREACH_HOLD_S):
                STATE["breach"] = {
                    "t": round(elapsed, 1), "users": users, "p95_ms": int(p95),
                    "rps": round(rps, 1), "error_rate": round(err_rate, 4),
                }
                _log(f"🔴 Point de rupture : ~{users} users actifs, "
                     f"p95 {int(p95)} ms (> {int(P95_MS)} ms)")
                if STOP_ON_BREACH:
                    return
        else:
            breach_since = None


@events.test_stop.add_listener
def _on_stop(environment, **_kwargs):
    if isinstance(environment.runner, WorkerRunner):
        return
    stats = environment.stats.total
    _sample_cpu(environment.runner)  # le moniteur s'arrete a la rupture, le test non
    if RESULT_PATH:
        try:
            with open(RESULT_PATH, "w", encoding="utf-8") as f:
                json.dump(_build_result(stats), f, ensure_ascii=False)
        except OSError:
            pass


def _capacity_rps():
    """Debit que l'injecteur a su produire : au point de saturation, sinon le pic vu."""
    if not CALIBRATION:
        return None
    breach = STATE["breach"]
    if breach:
        return breach["rps"]
    return max((row["rps"] for row in STATE["timeline"]), default=0)


def _build_result(stats):
    def pct(p):
        try:
            return round(stats.get_response_time_percentile(p), 1)
        except (TypeError, ValueError):
            return None
    def _pctl(samples, p):
        if not samples:
            return None
        ordered = sorted(samples)
        return round(ordered[min(len(ordered) - 1, int(p * len(ordered)))], 1)

    users_seen = [row["users"] for row in STATE["timeline"]] or [0]
    duration = (time.monotonic() - STATE["t0"]) if STATE["t0"] else 0
    breach = STATE["breach"]
    error_rate = round(stats.fail_ratio, 4)
    p99 = pct(0.99)
    tail_ok = P99_MS is None or p99 is None or p99 <= P99_MS
    data_received = getattr(stats, "total_content_length", 0) or 0
    checks_rate = (CHECKS["passed"] / CHECKS["total"]) if CHECKS["total"] else None
    throughput = STATE["throughput"] or {}
    return {
        "engine": "locust",
        "test_type": TEST_TYPE,
        "p50_ms": pct(0.5), "p95_ms": pct(0.95), "p99_ms": p99,
        "avg_ms": round(stats.avg_response_time, 1),
        "max_ms": round(stats.max_response_time, 1),
        # Requete la plus rapide = plancher incompressible (reseau + traitement au repos).
        "min_ms": round(stats.min_response_time, 1) if stats.min_response_time else None,
        "ttfb_p95_ms": _pctl(_TTFB_SAMPLES, 0.95),
        "reqs_total": stats.num_requests,
        "reqs_per_sec": round(stats.total_rps, 1),
        "error_rate": error_rate,
        "checks_rate": checks_rate,
        "data_received": data_received,
        "data_received_rate": round(data_received / duration, 1) if duration else 0,
        "data_sent": _DATA_SENT["bytes"],
        "data_sent_rate": round(_DATA_SENT["bytes"] / duration, 1) if duration else 0,
        "vus_max": max(users_seen),         # VRAI pic de users ACTIFS (pas « alloues »)
        "vus_target_max": max((u for _, u, _ in _PLAN), default=0),
        "vus_deficit_pct": round(STATE["vus_deficit"] * 100, 1),
        # Modele ferme : ecart entre le debit obtenu et celui que ces VUs auraient
        # produit sans ralentissement (cf. regle LOAD_CLOSED).
        "throughput_shortfall_pct": round(throughput["shortfall"] * 100, 1) if throughput else None,
        "throughput_nominal_rps": throughput.get("nominal_rps"),
        "throughput_actual_rps": throughput.get("rps"),
        "throughput_users": throughput.get("users"),
        "injector_capacity_rps": _capacity_rps(),
        "duration_s": round(duration, 1),
        # Locust n'echantillonne le CPU que toutes les 10 s et son 1er releve vaut 0 :
        # sous ~20 s de run il n'y a aucune mesure reelle -> None plutot qu'un « 0 % ».
        "injector_cpu_max": round(STATE["cpu_max"], 1) if STATE["cpu_max"] else None,
        "injector_cpu_warning": STATE["cpu_warning"] or STATE["cpu_max"] >= CPU_WARN_PCT,
        "seuil_p95_ms": P95_MS,
        "seuil_p99_ms": P99_MS,
        "breach": breach,                   # None si aucune rupture
        "timeline": STATE["timeline"],
        "stopped": STATE["stopped"] and breach is None,
        "thresholds_ok": breach is None and tail_ok and (error_rate * 100 <= ERROR_PCT),
    }
