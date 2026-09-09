import { afterEach, beforeEach, expect, test, vi } from 'vitest';

import { installDemoBackend } from './backend';

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
