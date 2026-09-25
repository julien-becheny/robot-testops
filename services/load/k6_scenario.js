// Scenario k6 (modele OUVERT) pilote par TestOps.
//
// Pendant que le locustfile pilote un NOMBRE d'utilisateurs, ce scenario impose un
// DEBIT : l'executeur `ramping-arrival-rate` lance N iterations par seconde quoi qu'il
// arrive, et compte dans `dropped_iterations` celles qu'il n'a pas pu lancer. C'est
// exactement ce que Locust ne sait pas faire (cf. regle LOAD_CLOSED).
//
// Tout arrive par variables d'environnement, comme pour le locustfile :
//   BASE_URL    : URL de base de la cible (liste blanche cote Python)
//   TARGET_ID   : identifiant d'une cible de services/load/targets.py -> choisit le scenario
//   TEST_TYPE   : type de test (open_load, ...)
//   PARAMS_JSON : parametres valides (rate, ramp_up, steady, ramp_down, p95_ms, ...)
//   RESULT_PATH : fichier ou ecrire le resultat final (meme format que Locust)
import http from 'k6/http';
import { check } from 'k6';

const PARAMS = JSON.parse(__ENV.PARAMS_JSON || '{}');
const TARGET_ID = __ENV.TARGET_ID || '';
const TEST_TYPE = __ENV.TEST_TYPE || 'open_load';
const BASE_URL = (__ENV.BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
const RESULT_PATH = __ENV.RESULT_PATH || 'k6_result.json';

const RATE = Number(PARAMS.rate ?? PARAMS.rate_max ?? 100);
const MAX_VUS = Number(PARAMS.max_vus || 400);
const P95_MS = Number(PARAMS.p95_ms || 800);
// Seuil de queue : seuls les types qui le declarent l'opposent au run.
const P99_MS = PARAMS.p99_ms ? Number(PARAMS.p99_ms) : null;
const ERROR_PCT = Number(PARAMS.error_pct || 1);

// Reserve de VUs ouverte d'emblee : au-dela k6 en alloue a chaud, ce qui coute une
// pause. On part sur une latence supposee de 0,5 s, plafonnee par le maximum autorise.
const PRE_ALLOCATED = Math.max(10, Math.min(MAX_VUS, Math.ceil(RATE * 0.5)));

// Paliers de debit : meme forme que le plan Locust, mais l'axe porte des req/s.
function stages() {
  if (TEST_TYPE === 'open_capacity') {
    const start = Number(PARAMS.rate_start || 50);
    const step = Math.max(1, Number(PARAMS.rate_step || 50));
    const ramp = PARAMS.ramp || '10s';
    const steady = PARAMS.steady || '30s';
    const plan = [];
    let level = Math.min(start, RATE);
    for (let n = 0; level <= RATE && n < 40; n += 1) {
      plan.push({ target: level, duration: ramp });
      plan.push({ target: level, duration: steady });
      level += step;
    }
    return plan;
  }
  if (TEST_TYPE === 'open_stress') {
    return [
      { target: RATE, duration: PARAMS.ramp_up || '1m' },
      { target: RATE, duration: PARAMS.peak_hold || '30s' },
      { target: 0, duration: PARAMS.ramp_down || '20s' },
    ];
  }
  return [
    { target: RATE, duration: PARAMS.ramp_up || '30s' },
    { target: RATE, duration: PARAMS.steady || '1m30s' },
    { target: 0, duration: PARAMS.ramp_down || '20s' },
  ];
}

// L'endurance n'a pas de rampe : un debit constant, tenu longtemps.
const SCENARIO_OPTIONS = TEST_TYPE === 'open_endurance'
  ? {
      executor: 'constant-arrival-rate',
      rate: RATE,
      timeUnit: '1s',
      duration: PARAMS.duration || '30m',
      preAllocatedVUs: PRE_ALLOCATED,
      maxVUs: MAX_VUS,
    }
  : {
      executor: 'ramping-arrival-rate',
      startRate: 0,
      timeUnit: '1s',
      preAllocatedVUs: PRE_ALLOCATED,
      maxVUs: MAX_VUS,
      stages: stages(),
    };

export const options = {
  scenarios: { flux: SCENARIO_OPTIONS },
  thresholds: {
    http_req_duration: P99_MS
      ? [`p(95)<${P95_MS}`, `p(99)<${P99_MS}`]
      : [`p(95)<${P95_MS}`],
    http_req_failed: [`rate<${ERROR_PCT / 100}`],
  },
  summaryTrendStats: ['min', 'avg', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
};

function doRoot() {
  const r = http.get(`${BASE_URL}/`, { tags: { name: '/' } });
  check(r, { 'page servie': (res) => res.status === 200 });
}

const SCENARIO = {
  quickpizza: doRoot,
};

export default function () {
  const scenario = SCENARIO[TARGET_ID];
  // Un repli par defaut enverrait des requetes hors sujet : des centaines d'erreurs
  // parfaitement plausibles, sans rien qui en nomme la cause.
  if (!scenario) throw new Error(`Aucun scenario k6 pour la cible « ${TARGET_ID} »`);
  scenario();
}

// ===== Resultat final, au MEME format que le locustfile =====
function metric(data, name) {
  const found = data.metrics && data.metrics[name];
  return (found && found.values) || {};
}

function round(value, digits = 1) {
  if (typeof value !== 'number' || !isFinite(value)) return null;
  const factor = Math.pow(10, digits);
  return Math.round(value * factor) / factor;
}

function failedThresholds(data) {
  const failed = [];
  Object.entries(data.metrics || {}).forEach(([name, m]) => {
    Object.entries(m.thresholds || {}).forEach(([expression, verdict]) => {
      if (verdict && verdict.ok === false) failed.push(`${name}: ${expression}`);
    });
  });
  return failed;
}

function buildResult(data) {
  const duration = metric(data, 'http_req_duration');
  const waiting = metric(data, 'http_req_waiting');
  const reqs = metric(data, 'http_reqs');
  const failedRate = metric(data, 'http_req_failed').rate;
  const checks = metric(data, 'checks').rate;
  const received = metric(data, 'data_received');
  const sent = metric(data, 'data_sent');
  const dropped = metric(data, 'dropped_iterations').count || 0;
  const iterations = metric(data, 'iterations').count || 0;
  const runMs = (data.state && data.state.testRunDurationMs) || 0;
  const failed = failedThresholds(data);
  // Le debit VISE par le plan : ce que l'executeur aurait lance sans blocage.
  const attempted = iterations + dropped;

  return {
    engine: 'k6',
    model: 'open',
    test_type: TEST_TYPE,
    p50_ms: round(duration.med),
    p95_ms: round(duration['p(95)']),
    p99_ms: round(duration['p(99)']),
    avg_ms: round(duration.avg),
    max_ms: round(duration.max),
    min_ms: round(duration.min),
    ttfb_p95_ms: round(waiting['p(95)']),
    reqs_total: reqs.count || 0,
    reqs_per_sec: round(reqs.rate),
    error_rate: round(failedRate, 4),
    checks_rate: typeof checks === 'number' ? round(checks, 4) : null,
    data_received: received.count || 0,
    data_received_rate: round(received.rate),
    data_sent: sent.count || 0,
    data_sent_rate: round(sent.rate),
    vus_max: metric(data, 'vus_max').value || metric(data, 'vus_max').max || null,
    // Specifique au modele ouvert : ce que l'injecteur n'a PAS reussi a lancer.
    dropped_iterations: dropped,
    dropped_pct: attempted ? round((dropped / attempted) * 100) : 0,
    rate_target: RATE,
    max_vus_allowed: MAX_VUS,
    duration_s: round(runMs / 1000),
    seuil_p95_ms: P95_MS,
    seuil_p99_ms: P99_MS,
    thresholds_ok: failed.length === 0,
    failed_thresholds: failed,
  };
}

export function handleSummary(data) {
  const result = buildResult(data);
  return {
    [RESULT_PATH]: JSON.stringify(result),
    stdout: `\nk6 termine - p95 ${result.p95_ms} ms · ${result.reqs_total} req · ` +
      `${result.dropped_iterations} iteration(s) non lancee(s)\n`,
  };
}
