/**
 * Backend simulé pour la démonstration publique.
 *
 * `window.fetch` est dérouté vers des données figées, capturées sur une vraie
 * installation, et chaque lancement rejoue une session réellement exécutée (mêmes
 * tests, mêmes étapes, mêmes mesures, ramenées à l'échelle d'une visite). Aucun
 * navigateur n'est piloté, aucun test ne tourne.
 */
import fixtures from './fixtures.json';
import analyse from './analyse.json';
import mobile from './mobile.json';
import { campaignRoutes } from './campaigns';
import { json, matching } from './http';
import { loadRoutes } from './load';
import {
  activeSessions,
  nextSessionId,
  recordedRun,
  runTimeline,
  startSession,
  stopSession,
} from './replay';

// Les liens de rapport sont des fichiers statiques déposés par session (voir public/logs/).
const MAX_SESSIONS = 9;

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '');

// services/execution/commands.py : ces tests ne partent jamais dans un run habituel.
const EXCLUDED_TAGS = ['not_ready', 'in_dev', 'blocked', 'deprecated', 'appium', 'quarantaine'];

// api/validation.py : le viewport envoyé par l'interface désigne l'appareil émulé.
const VIEWPORT_DEVICES = { '1920x1080': 'desktop', '768x1024': 'tablet', '375x812': 'mobile' };

// Le serveur Appium enregistré démarre à la demande et reste en ligne après un run.
let appiumOnline = false;

const replayRun = (prefix, max, tests) => {
  const sessionId = nextSessionId(prefix, max);
  startSession(sessionId, runTimeline(sessionId, tests));
  return sessionId;
};

const runSmoke = () =>
  json({ status: 'started', session_id: replayRun('demo', MAX_SESSIONS, fixtures.run.tests) });

const sample = (names, count) => {
  const pool = [...names];
  for (let i = pool.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [pool[i], pool[j]] = [pool[j], pool[i]];
  }
  return pool.slice(0, count);
};

/** Rejoue, sur la cible demandée, les résultats réels des tests que les tags sélectionnent. */
const runByTags = (body) => {
  const browser = String(body?.browser || 'chromium').toLowerCase();
  const device = VIEWPORT_DEVICES[body?.viewport] || 'desktop';
  let names = matching(body?.include_tags, [...(body?.exclude_tags || []), ...EXCLUDED_TAGS]).map(
    (test) => test.name
  );
  if (body?.is_random) {
    const wanted = Number(body.nb_selection) || 0;
    names = sample(names, wanted > 0 ? Math.min(wanted, names.length) : names.length);
  }
  const { tests, notes } = recordedRun(browser, device, names);
  const sessionId = nextSessionId(`${browser}-${device}`, 3);
  startSession(sessionId, runTimeline(sessionId, tests, { notes }));
  return json({ status: 'started', session_id: sessionId });
};

// [méthode, chemin exact ou motif, handler] ; « * » accepte toute méthode.
const routes = [
  ['*', '/environments', () => json(fixtures.environments)],
  ['*', '/git-info', () => json(fixtures.gitInfo)],
  ['*', '/smoke-suite', () => json(fixtures.smokeSuite)],
  ['*', '/available-tags', () => json(fixtures.catalogue)],
  [
    '*',
    '/execution-status',
    () => json({ is_running: activeSessions() > 0, running_count: activeSessions(), sessions: [] }),
  ],
  [
    '*',
    '/config-vars',
    (body) => {
      if (body?.key) fixtures.configVars[body.key] = body.value;
      return json(fixtures.configVars);
    },
  ],
  [
    '*',
    '/matching-tests',
    (body) => {
      const tests = matching(body?.include_tags, body?.exclude_tags);
      return json({ count: tests.length, tests });
    },
  ],
  ['*', '/run-test', runSmoke],
  ['*', '/run-by-tags', runByTags],
  [
    '*',
    '/stop-test',
    (body) => {
      stopSession(body?.session_id);
      return json({ status: 'stopping' });
    },
  ],
  ['GET', '/coverage', () => json(analyse.coverage)],
  ['POST', '/coverage/export', () => json(analyse.coverageExport)],
  ['GET', '/suite-health', () => json(analyse.suiteHealth)],
  ['GET', '/run-diff', () => json(analyse.runDiff)],
  [
    'GET',
    '/mobile-preflight',
    () => json(appiumOnline ? mobile.preflightOnline : mobile.preflight),
  ],
  [
    'POST',
    '/mobile/appium/start',
    () => {
      appiumOnline = true;
      return json(mobile.appiumStart);
    },
  ],
  [
    'POST',
    '/mobile/appium/stop',
    () => {
      appiumOnline = false;
      return json(mobile.appiumStop);
    },
  ],
  [
    'POST',
    '/run-appium',
    () => {
      appiumOnline = true;
      return json({
        status: 'started',
        session_id: replayRun('appium', 3, mobile.run),
        message: 'Run mobile Appium lancé',
      });
    },
  ],
  ...campaignRoutes,
  ...loadRoutes,
];

const findRoute = (method, path) => {
  for (const [verb, pattern, handler] of routes) {
    if (verb !== '*' && verb !== method) continue;
    if (typeof pattern === 'string') {
      if (pattern === path) return { handler, params: [] };
    } else {
      const found = path.match(pattern);
      if (found) return { handler, params: found.slice(1) };
    }
  }
  return null;
};

/** Installe le backend simulé : à appeler avant le premier rendu. */
export const installDemoBackend = () => {
  const realFetch = window.fetch.bind(window);

  window.fetch = async (input, init = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, window.location.origin);
    const path = url.pathname.replace(BASE, '') || '/';
    const method = (init.method || 'GET').toUpperCase();
    const route = findRoute(method, path);

    // Les rapports et les ressources du site sont de vrais fichiers : ne pas les intercepter.
    if (!route) return realFetch(input, init);

    const body = init.body ? JSON.parse(init.body) : null;
    return route.handler(body, { params: route.params, query: url.searchParams, method });
  };
};
