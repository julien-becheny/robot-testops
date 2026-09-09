/**
 * Backend simulé pour la démonstration publique.
 *
 * `window.fetch` est dérouté vers des données figées, capturées sur une vraie
 * installation, et un lancement rejoue la chronologie d'un run Robot Framework
 * réellement exécuté (mêmes tests, mêmes étapes, mêmes durées, ramenées à
 * l'échelle d'une visite). Aucun navigateur n'est piloté, aucun test ne tourne.
 */
import fixtures from './fixtures.json';
import { emit } from './bus';

// Le run rejoué dure 9,3 s en vrai : personne ne regarde une démonstration aussi longtemps.
const SPEED = 0.3;
const STEP_FLOOR_MS = 90;

// Les liens de rapport sont des fichiers statiques déposés par session (voir public/logs/).
const MAX_SESSIONS = 9;

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '');

const sessions = new Map();
let sessionCounter = 0;

const json = (body) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });

const matching = (include = [], exclude = []) =>
  fixtures.tests.filter((test) => {
    const tags = test.tags || [];
    if (exclude.some((tag) => tags.includes(tag))) return false;
    return include.length === 0 || include.some((tag) => tags.includes(tag));
  });

/** Programme une suite d'actions datées et rend de quoi toutes les annuler. */
const schedule = (actions) => {
  const timers = actions.map(({ at, run }) => setTimeout(run, at));
  return () => timers.forEach(clearTimeout);
};

/** Construit la chronologie d'un run à partir du scénario capturé. */
const buildTimeline = (sessionId, tests) => {
  const actions = [];
  const counts = { passed: 0, failed: 0, skipped: 0 };
  let clock = 300;

  const log = (message, level = 'info') =>
    actions.push({ at: clock, run: () => emit('log', { message, level, session_id: sessionId }) });

  tests.forEach((test) => {
    const duration = Math.max(test.elapsed * SPEED, test.steps.length * STEP_FLOOR_MS);
    const perStep = duration / Math.max(test.steps.length, 1);

    log(`🧪 Test: ${test.name}`);

    test.steps.forEach((step) => {
      clock += perStep;
      log(step.name, step.failed ? 'keyword-failed' : 'keyword');
    });

    clock += perStep / 2;
    if (test.status === 'PASS') {
      counts.passed += 1;
      log("✅ Le test s'est exécuté avec succès");
    } else {
      counts.failed += 1;
      log('❌ Le test a échoué');
    }

    const done = counts.passed + counts.failed + counts.skipped;
    actions.push({
      at: clock,
      run: () => {
        emit('test-result', {
          name: test.name,
          longname: test.name,
          status: test.status,
          message: '',
          elapsed: test.elapsed,
          session_id: sessionId,
        });
        emit('progress', { done, total: tests.length, phase: 'run', session_id: sessionId });
      },
    });
  });

  clock += 400;
  actions.push({
    at: clock,
    run: () => {
      emit('final-status', {
        status: `${tests.length} tests, ${counts.passed} passed, ${counts.failed} failed`,
        session_id: sessionId,
        ...counts,
        total: tests.length,
      });
      emit('log-link', { log_link: 'log.html', session_id: sessionId });
      emit('execution-complete', { session_id: sessionId });
      sessions.delete(sessionId);
    },
  });

  return actions;
};

const startSession = () => {
  if (sessions.size === 0) sessionCounter = 0;
  sessionCounter = (sessionCounter % MAX_SESSIONS) + 1;
  const sessionId = `demo-${sessionCounter}`;

  const cancel = schedule(buildTimeline(sessionId, fixtures.run.tests));
  sessions.set(sessionId, { cancel });
  return sessionId;
};

const stopSession = (sessionId) => {
  const session = sessions.get(sessionId);
  if (!session) return;
  session.cancel();
  sessions.delete(sessionId);
  emit('log', {
    message: '⏹️ Arrêt demandé : exécution interrompue',
    level: 'info',
    session_id: sessionId,
  });
  emit('execution-complete', { session_id: sessionId });
};

const routes = {
  '/environments': () => json(fixtures.environments),
  '/git-info': () => json(fixtures.gitInfo),
  '/smoke-suite': () => json(fixtures.smokeSuite),
  '/available-tags': () => json(fixtures.catalogue),
  '/execution-status': () =>
    json({ is_running: sessions.size > 0, running_count: sessions.size, sessions: [] }),
  '/config-vars': (body) => {
    if (body?.key) fixtures.configVars[body.key] = body.value;
    return json(fixtures.configVars);
  },
  '/matching-tests': (body) => {
    const tests = matching(body?.include_tags, body?.exclude_tags);
    return json({ count: tests.length, tests });
  },
  '/run-test': () => json({ status: 'started', session_id: startSession() }),
  '/run-by-tags': () => json({ status: 'started', session_id: startSession() }),
  '/stop-test': (body) => {
    stopSession(body?.session_id);
    return json({ status: 'stopping' });
  },
};

/** Installe le backend simulé : à appeler avant le premier rendu. */
export const installDemoBackend = () => {
  const realFetch = window.fetch.bind(window);

  window.fetch = async (input, init = {}) => {
    const url = typeof input === 'string' ? input : input.url;
    const path = new URL(url, window.location.origin).pathname.replace(BASE, '') || '/';
    const handler = routes[path];

    // Les rapports et les ressources du site sont de vrais fichiers : ne pas les intercepter.
    if (!handler) return realFetch(input, init);

    const body = init.body ? JSON.parse(init.body) : null;
    return handler(body);
  };
};
