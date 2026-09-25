import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';

import { installDemoBackend } from './backend';
import { on } from './bus';

let realFetch;

beforeEach(() => {
  realFetch = vi.fn(async () => new Response('fichier', { status: 200 }));
  window.fetch = realFetch;
  installDemoBackend();
});

afterEach(() => {
  vi.restoreAllMocks();
});

test('répond aux routes de l’API sans toucher au réseau', async () => {
  const res = await fetch('http://localhost:5001/available-tags');
  const data = await res.json();

  expect(data.total_tests).toBeGreaterThan(0);
  expect(realFetch).not.toHaveBeenCalled();
});

test('filtre les tests sur les tags demandés', async () => {
  const res = await fetch('http://localhost:5001/matching-tests', {
    method: 'POST',
    body: JSON.stringify({ include_tags: ['smoke'], exclude_tags: [] }),
  });
  const data = await res.json();

  expect(data.count).toBe(data.tests.length);
  expect(data.tests.every((t) => t.tags.includes('smoke'))).toBe(true);
});

// Le rapport d'un run est un vrai fichier servi par le site : l'avaler renverrait
// une erreur à la place du log Robot Framework.
test('laisse passer ce qui n’est pas une route de l’API', async () => {
  const res = await fetch('/logs/demo-1/standard/log.html');

  expect(realFetch).toHaveBeenCalledOnce();
  expect(res.status).toBe(200);
});

const post = (path, body) =>
  fetch(`http://localhost:5001${path}`, { method: 'POST', body: JSON.stringify(body) });

const get = async (path) => (await fetch(`http://localhost:5001${path}`)).json();

/** Enregistre les événements diffusés, dans l'ordre, pour les noms demandés. */
const record = (...names) => {
  const seen = [];
  names.forEach((name) => on(name, (payload) => seen.push({ name, payload })));
  return seen;
};

describe('sessions rejouées', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  test('un lot de campagne bascule ses cellules avant de rendre la main', async () => {
    const { campaigns } = await get('/campaigns');
    const [campaign] = campaigns;
    const todo = async () =>
      (await get(`/campaigns/${campaign.id}/cells`)).cells.filter(
        (c) => c.browser === 'webkit' && c.device === 'mobile' && c.status === 'todo'
      ).length;
    const before = await todo();
    const seen = record('campaign_updated', 'execution-complete');

    const data = await (
      await post(`/campaigns/${campaign.id}/run`, { browser: 'webkit', device: 'mobile', count: 3 })
    ).json();
    vi.runAllTimers();

    expect(data.session_id).toMatch(/^webkit-mobile-/);
    expect(await todo()).toBe(before - 3);
    expect(seen.map((e) => e.name)).toEqual(['campaign_updated', 'execution-complete']);
  });

  test('une exécution par tags rejoue les tests sélectionnés, sur la cible demandée', async () => {
    const { tests: selected } = await (
      await post('/matching-tests', { include_tags: ['cart'], exclude_tags: [] })
    ).json();
    const seen = record('test-result');

    const data = await (
      await post('/run-by-tags', { include_tags: ['cart'], browser: 'webkit', viewport: '375x812' })
    ).json();
    vi.runAllTimers();

    expect(data.session_id).toMatch(/^webkit-mobile-/);
    expect(seen).toHaveLength(4);
    expect(seen.map((e) => e.payload.name).sort()).toEqual(selected.map((t) => t.name).sort());
  });

  // services/execution/commands.py exclut `appium` de tout run habituel : la démo aussi.
  test('une exécution par tags laisse de côté les tests qui exigent un appareil', async () => {
    const seen = record('test-result');

    await post('/run-by-tags', { include_tags: ['appium', 'multi_moteur'], viewport: '1920x1080' });
    vi.runAllTimers();

    expect(seen.map((e) => e.payload.name)).toEqual([
      "Achat - Deux Articles Jusqu'à La Confirmation",
    ]);
  });

  test('une exécution aléatoire rejoue le nombre de tests demandé', async () => {
    const seen = record('test-result');

    await post('/run-by-tags', {
      include_tags: ['saucedemo'],
      is_random: true,
      nb_selection: 3,
      browser: 'chromium',
      viewport: '1920x1080',
    });
    vi.runAllTimers();

    expect(new Set(seen.map((e) => e.payload.name)).size).toBe(3);
  });

  test('une cible jamais jouée en vrai le dit au lieu de rejouer une autre cible', async () => {
    const seen = record('log', 'test-result', 'execution-complete');

    await post('/run-by-tags', {
      include_tags: ['cart'],
      browser: 'firefox',
      viewport: '768x1024',
    });
    vi.runAllTimers();

    expect(seen.some((e) => e.name === 'test-result')).toBe(false);
    expect(seen[0].payload.message).toMatch(/aucun run réel/);
    expect(seen.at(-1).name).toBe('execution-complete');
  });

  test('refuse une cible que la campagne ne couvre pas', async () => {
    const [campaign] = (await get('/campaigns')).campaigns;

    const res = await post(`/campaigns/${campaign.id}/run`, {
      browser: 'firefox',
      device: 'tablet',
    });

    expect(res.status).toBe(400);
  });

  test('un test de charge rejoue les mesures du run réel, puis son verdict', async () => {
    const before = (await get('/load-history')).runs.length;
    const seen = record('load-metrics', 'load-result', 'execution-complete');

    await post('/run-load', { target: 'quickpizza', test_type: 'smoke', params: {} });
    vi.runAllTimers();

    const names = seen.map((e) => e.name);
    const result = seen.find((e) => e.name === 'load-result').payload.result;
    expect(names.filter((n) => n === 'load-metrics')).toHaveLength(result.timeline.length);
    expect(names.slice(-2)).toEqual(['load-result', 'execution-complete']);
    expect((await get('/load-history')).runs).toHaveLength(before + 1);
  });

  // Un type jamais joué en vrai ne doit pas produire de chiffres inventés.
  test('un type de charge sans run réel le dit et s’arrête', async () => {
    const seen = record('log', 'load-result', 'execution-complete');

    await post('/run-load', { target: 'quickpizza', test_type: 'stress', params: {} });
    vi.runAllTimers();

    expect(seen.some((e) => e.name === 'load-result')).toBe(false);
    expect(seen[0].payload.message).toMatch(/aucun run réel/);
    expect(seen.at(-1).name).toBe('execution-complete');
  });

  test('l’arrêt manuel coupe un rejeu avant son verdict', async () => {
    const seen = record('load-result', 'execution-complete');

    const { session_id: sessionId } = await (
      await post('/run-load', { target: 'quickpizza', test_type: 'smoke', params: {} })
    ).json();
    vi.advanceTimersByTime(500);
    await post('/stop-test', { session_id: sessionId });
    vi.runAllTimers();

    expect(seen.map((e) => e.name)).toEqual(['execution-complete']);
  });

  test('un run mobile rejoue les échecs avec leur message, Appium reste en ligne', async () => {
    const seen = record('log');

    await post('/run-appium');
    vi.runAllTimers();

    expect(seen.some((e) => e.payload.message.startsWith('Message: '))).toBe(true);
    expect((await get('/mobile-preflight')).appium_online).toBe(true);
  });
});
