/**
 * Tests de charge simulés : chaque lancement rejoue le dernier run réel de son type sur
 * QuickPizza - mêmes mesures, même verdict, même rapport - en une vingtaine de secondes.
 *
 * Un type jamais joué en vrai n'est pas inventé : la session le dit et s'arrête.
 */
import load from './load.json';
import { emit } from './bus';
import { json } from './http';
import { nextSessionId, startSession } from './replay';

const REPLAY_MS = 18000;
const METRIC_STEP_MAX_MS = 2000;

// services/load/baselines.py : les seuils jugent un run sans changer la charge appliquée.
const THRESHOLDS = ['p95_ms', 'p99_ms', 'error_pct'];
const METRICS = [
  'p50_ms',
  'p95_ms',
  'p99_ms',
  'min_ms',
  'reqs_per_sec',
  'error_rate',
  'checks_rate',
  'injector_capacity_rps',
];

const recorded = new Map(load.history.map((run) => [run.id, run]));
const history = [...load.history];
const baselines = { ...load.baselines };

const baselineKey = (target, testType) => `${target}|${testType}`;

const engineOf = (testType) => {
  const model = load.profiles.types.find((t) => t.id === testType)?.model;
  return load.profiles.models.find((m) => m.id === model)?.engine || 'locust';
};

const reference = (run) => {
  const result = run.result || {};
  const metrics = Object.fromEntries(
    METRICS.filter((m) => result[m] !== undefined && result[m] !== null).map((m) => [m, result[m]])
  );
  if (result.breach?.users != null) metrics.breach_users = result.breach.users;
  if (result.breach?.rps != null) metrics.breach_rps = result.breach.rps;
  return {
    run_id: run.id,
    ts: run.ts,
    label: run.target_label || run.target,
    params: Object.fromEntries(
      Object.entries(run.params || {}).filter(([k]) => !THRESHOLDS.includes(k))
    ),
    metrics,
  };
};

const replay = (sessionId, testType) => {
  const actions = [];
  const log = (at, message) =>
    actions.push({ at, run: () => emit('log', { message, level: 'info', session_id: sessionId }) });

  const plan = load.replays[testType];
  if (!plan) {
    log(
      200,
      `ℹ️ Démonstration : aucun run réel de type ${testType} n'a été enregistré sur cette cible. ` +
        `Types rejoués : ${Object.keys(load.replays).join(', ')}.`
    );
    actions.push({ at: 400, run: () => emit('execution-complete', { session_id: sessionId }) });
    return actions;
  }

  const run = recorded.get(plan.run_id);
  const date = new Date(run.ts * 1000).toLocaleString('fr-FR', {
    dateStyle: 'long',
    timeStyle: 'short',
  });
  log(100, `ℹ️ Démonstration : rejoue le run réel du ${date}, avec ses paramètres d'origine.`);
  plan.start.forEach((line, i) => log(300 + i * 400, line));

  const points = run.result.timeline;
  const step = Math.min(METRIC_STEP_MAX_MS, REPLAY_MS / points.length);
  let clock = 1200;
  points.forEach((point) => {
    clock += step;
    const metrics = {
      vus: point.users,
      vus_target: null,
      vus_lagging: false,
      cpu: null,
      reqs_per_sec: point.rps,
      p95_ms: point.p95_ms,
      error_rate: point.error_rate,
    };
    if (point.dropped !== undefined) metrics.dropped = point.dropped;
    actions.push({
      at: clock,
      run: () => emit('load-metrics', { metrics, session_id: sessionId }),
    });
  });

  clock += 600;
  log(clock, plan.verdict);
  actions.push({
    at: clock + 50,
    run: () => {
      emit('load-result', { result: run.result, session_id: sessionId });
      history.unshift({
        ...run,
        id: Math.random().toString(16).slice(2, 14),
        ts: Date.now() / 1000,
      });
      emit('execution-complete', { session_id: sessionId });
    },
  });
  return actions;
};

export const loadRoutes = [
  ['GET', '/load-targets', () => json(load.targets)],
  ['GET', '/load-profiles', () => json(load.profiles)],
  [
    'POST',
    '/run-load',
    (body) => {
      const sessionId = nextSessionId('charge', 3);
      startSession(sessionId, replay(sessionId, body?.test_type));
      return json({
        status: 'started',
        session_id: sessionId,
        engine: engineOf(body?.test_type),
        // Pas de dashboard Locust ou k6 : aucun injecteur ne tourne derrière la démonstration.
        dashboard_url: null,
      });
    },
  ],
  ['GET', '/load-history', () => json({ runs: history.slice(0, 50) })],
  [
    'DELETE',
    '/load-history',
    () => {
      history.length = 0;
      return json({ status: 'ok' });
    },
  ],
  ['GET', '/load-baselines', () => json({ baselines })],
  [
    'GET',
    '/load-baseline',
    (body, { query }) =>
      json({
        baseline: baselines[baselineKey(query.get('target'), query.get('test_type'))] || null,
      }),
  ],
  [
    'POST',
    '/load-baseline',
    (body) => {
      const run = history.find((r) => r.id === body?.run_id);
      if (!run) return json({ error: 'Run introuvable dans l historique' }, 404);
      if (run.result?.error) return json({ error: 'Ce run ne peut pas servir de reference' }, 400);
      const baseline = reference(run);
      baselines[baselineKey(run.target, run.test_type)] = baseline;
      return json({ baseline });
    },
  ],
  [
    'DELETE',
    '/load-baseline',
    (body) => {
      const key = baselineKey(body?.target, body?.test_type);
      const removed = key in baselines;
      delete baselines[key];
      return json({ status: 'ok', removed });
    },
  ],
];
