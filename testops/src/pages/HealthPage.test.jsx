import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';

import HealthPage from './HealthPage';

const buildTest = (overrides) => ({
  test: 'test_suites/web/00_smoke.robot::Connexion',
  name: 'Connexion',
  source: 'test_suites/web/00_smoke.robot',
  runs: 6,
  passed: 6,
  failed: 0,
  statuses: ['PASS', 'PASS', 'PASS', 'PASS', 'PASS', 'PASS'],
  median_ms: 2680,
  last_message: null,
  verdict: 'stable',
  quarantined: false,
  runs_since: 0,
  ...overrides,
});

const emptyDiff = {
  run: null,
  baseline: null,
  same_commit: false,
  counts: {},
  changes: [],
};

// La page interroge deux endpoints : router par URL, sinon le diff reçoit la santé.
const installFetch = (payload, diff = emptyDiff) => {
  global.fetch = vi.fn(async (url) => ({
    ok: true,
    json: async () => (String(url).includes('/run-diff') ? diff : payload),
  }));
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

test('annonce le verdict et la durée médiane de chaque test', async () => {
  installFetch({
    window: 30,
    runs: 6,
    counts: { instable: 0, cassé: 0, neuf: 0, stable: 1 },
    quarantined: 0,
    tests: [buildTest()],
  });

  render(<HealthPage />);

  expect(await screen.findByText('Connexion')).toBeInTheDocument();
  // « Stable » nomme aussi le filtre : on vise la pastille de la ligne.
  expect(screen.getByText('Stable', { selector: '.health-verdict' })).toBeInTheDocument();
  expect(screen.getByText('6/6')).toBeInTheDocument();
  expect(screen.getByText('2.7 s')).toBeInTheDocument();
});

test('filtre sur un verdict sans perdre le reste du rapport', async () => {
  installFetch({
    window: 30,
    runs: 8,
    counts: { instable: 1, cassé: 0, neuf: 0, stable: 1 },
    quarantined: 0,
    tests: [
      buildTest({
        test: 'a.robot::Panier',
        name: 'Panier',
        verdict: 'instable',
        passed: 4,
        runs: 8,
        last_message: 'Élément introuvable',
      }),
      buildTest(),
    ],
  });

  render(<HealthPage />);

  expect(await screen.findByText('Panier')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Instable 1' }));

  expect(screen.getByText('Panier')).toBeInTheDocument();
  expect(screen.queryByText('Connexion')).not.toBeInTheDocument();
  expect(screen.getByText('Élément introuvable')).toBeInTheDocument();
});

test('signale depuis combien de runs un test est mis de côté', async () => {
  installFetch({
    window: 30,
    runs: 12,
    counts: { instable: 0, cassé: 0, neuf: 1, stable: 0 },
    quarantined: 1,
    tests: [buildTest({ verdict: 'neuf', quarantined: true, runs_since: 12 })],
  });

  render(<HealthPage />);

  expect(await screen.findByText(/En quarantaine · 12 runs/)).toBeInTheDocument();
});

test("le dit franchement quand aucun run n'a encore été enregistré", async () => {
  installFetch({ window: 30, runs: 0, counts: {}, quarantined: 0, tests: [] });

  render(<HealthPage />);

  expect(await screen.findByText(/Aucun run enregistré/)).toBeInTheDocument();
});

test('affiche un message clair si le backend ne répond pas', async () => {
  global.fetch = vi.fn(async () => {
    throw new Error('offline');
  });

  render(<HealthPage />);

  expect(await screen.findByText(/n'a pas pu être chargée/)).toBeInTheDocument();
});

const health = { window: 30, runs: 6, counts: {}, quarantined: 0, tests: [buildTest()] };

const buildChange = (overrides) => ({
  test: 'a.robot::Panier',
  name: 'Panier',
  source: 'a.robot',
  change: 'regression',
  status: 'FAIL',
  previous_status: 'PASS',
  message: 'Élément introuvable',
  flaky: false,
  ...overrides,
});

const buildDiff = (changes, overrides = {}) => ({
  run: { id: 'run_2', ts: 1757145330, commit: 'def456' },
  baseline: { id: 'run_1', ts: 1757058930, commit: 'abc123' },
  same_commit: false,
  counts: changes.reduce(
    (acc, change) => ({ ...acc, [change.change]: (acc[change.change] || 0) + 1 }),
    {}
  ),
  changes,
  ...overrides,
});

const openDiff = () => fireEvent.click(screen.getByRole('button', { name: /Ce qui a changé/ }));

test('nomme les régressions et les deux commits comparés', async () => {
  installFetch(health, buildDiff([buildChange()]));

  render(<HealthPage />);
  await screen.findByText('Connexion');
  openDiff();

  expect(screen.getByText('Régression', { selector: '.health-verdict' })).toBeInTheDocument();
  expect(screen.getByText('Panier')).toBeInTheDocument();
  expect(screen.getByText('abc123 → def456')).toBeInTheDocument();
});

test('ne fait sonner le compteur que pour les régressions sûres', async () => {
  installFetch(
    health,
    buildDiff([buildChange({ flaky: true }), buildChange({ test: 'b.robot::Achat' })])
  );

  render(<HealthPage />);
  await screen.findByText('Connexion');

  // Deux régressions, mais une seule est digne de confiance.
  expect(screen.getByRole('button', { name: 'Ce qui a changé 1' })).toBeInTheDocument();
});

test('avertit quand le code est resté le même des deux côtés', async () => {
  installFetch(
    health,
    buildDiff([buildChange()], {
      same_commit: true,
      run: { id: 'run_2', ts: 1757145330, commit: 'abc123' },
    })
  );

  render(<HealthPage />);
  await screen.findByText('Connexion');
  openDiff();

  expect(screen.getByText(/Le code n'a pas bougé/)).toBeInTheDocument();
  expect(screen.getByText('même commit abc123')).toBeInTheDocument();
});

test("le dit quand la configuration n'a jamais tourné avant", async () => {
  installFetch(health, { ...emptyDiff, run: { id: 'run_1', ts: 1757145330, commit: 'abc123' } });

  render(<HealthPage />);
  await screen.findByText('Connexion');
  openDiff();

  expect(screen.getByText(/Premier run de cette configuration/)).toBeInTheDocument();
});

test('un diff absent ne prive pas la page de son contenu principal', async () => {
  global.fetch = vi.fn(async (url) => {
    if (String(url).includes('/run-diff')) throw new Error('offline');
    return { ok: true, json: async () => health };
  });

  render(<HealthPage />);

  expect(await screen.findByText('Connexion')).toBeInTheDocument();
});
