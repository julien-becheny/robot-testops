/**
 * Sessions rejouées : les événements qu'un vrai run diffuse, dans le même ordre, à
 * l'échelle d'une visite.
 *
 * Une session est une liste d'actions datées. Le registre sait lesquelles tournent,
 * pour `/execution-status`, et les arrête sur `/stop-test`.
 */
import fixtures from './fixtures.json';
import { emit } from './bus';

// Un run réel dure de quelques secondes à plusieurs minutes : personne ne regarde une
// démonstration aussi longtemps.
const SPEED = 0.3;
const STEP_FLOOR_MS = 90;

const REPLAYED_TARGETS = Object.keys(fixtures.results)
  .map((target) => target.replace('-', ' · '))
  .join(', ');

const sessions = new Map();
const counters = new Map();

export const activeSessions = () => sessions.size;

/**
 * Les résultats réels de ces tests sur cette cible, et ce qu'il faut dire des autres :
 * un test qu'aucun run n'a joué sur la cible n'est pas inventé.
 */
export const recordedRun = (browser, device, names) => {
  const recorded = fixtures.results[`${browser}-${device}`];
  const tests = names.map((name) => recorded?.find((t) => t.name === name)).filter(Boolean);
  const missing = names.length - tests.length;
  const notes = [];
  if (missing > 0 && recorded) {
    notes.push(
      `ℹ️ Démonstration : ${missing} test(s) sans run réel enregistré sur ${browser} · ${device}, non rejoué(s).`
    );
  } else if (missing > 0) {
    notes.push(
      `ℹ️ Démonstration : aucun run réel n'a été enregistré sur ${browser} · ${device}. Cibles rejouées : ${REPLAYED_TARGETS}.`
    );
  }
  return { tests, notes };
};

/**
 * Identifiant de session cyclique : chaque rapport est un fichier statique déposé par
 * session (voir public/logs/), il en existe donc un nombre fini par préfixe.
 */
export const nextSessionId = (prefix, max) => {
  if (sessions.size === 0) counters.clear();
  const n = ((counters.get(prefix) || 0) % max) + 1;
  counters.set(prefix, n);
  return `${prefix}-${n}`;
};

/** Programme les actions d'une session ; elle quitte le registre après la dernière. */
export const startSession = (sessionId, actions) => {
  sessions.get(sessionId)?.cancel();
  const end = actions.reduce((last, action) => Math.max(last, action.at), 0);
  const timers = [...actions, { at: end, run: () => sessions.delete(sessionId) }].map(
    ({ at, run }) => setTimeout(run, at)
  );
  sessions.set(sessionId, { cancel: () => timers.forEach(clearTimeout) });
};

export const stopSession = (sessionId) => {
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

/**
 * Chronologie d'un run Robot Framework rejoué à partir de tests enregistrés, avec les
 * messages du listener (robot_listeners/execution_listener.py).
 *
 * `after` s'exécute juste avant `execution-complete`, comme la mise à jour d'une
 * campagne côté backend.
 */
export const runTimeline = (sessionId, tests, { notes = [], after = [] } = {}) => {
  const actions = [];
  const counts = { passed: 0, failed: 0, skipped: 0 };
  let clock = 300;

  const log = (message, level = 'info') =>
    actions.push({ at: clock, run: () => emit('log', { message, level, session_id: sessionId }) });

  notes.forEach((note) => log(note));

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
    } else if (test.status === 'SKIP') {
      counts.skipped += 1;
      log('⏭️ Le test a été ignoré');
    } else {
      counts.failed += 1;
      log('❌ Le test a échoué');
      if (test.message) log(`Message: ${test.message}`);
    }

    const done = counts.passed + counts.failed + counts.skipped;
    actions.push({
      at: clock,
      run: () => {
        emit('test-result', {
          name: test.name,
          longname: test.longname || test.name,
          status: test.status,
          message: test.message || '',
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
      if (tests.length > 0) {
        emit('final-status', {
          status: `${tests.length} tests, ${counts.passed} passed, ${counts.failed} failed`,
          session_id: sessionId,
          ...counts,
          total: tests.length,
        });
        emit('log-link', { log_link: 'log.html', session_id: sessionId });
      }
      after.forEach((fn) => fn());
      emit('execution-complete', { session_id: sessionId });
    },
  });

  return actions;
};
