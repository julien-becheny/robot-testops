import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';

import { HistoryCard } from './history';

afterEach(cleanup);

const run = (id, engine, model, params, ts) => ({
  id,
  ts,
  test_type: model === 'open' ? 'open_load' : 'load',
  target_label: 'Lab local',
  params,
  result: {
    engine,
    model,
    status: 'ok',
    p95_ms: model === 'open' ? 5058 : 300,
    p99_ms: 5100,
    ttfb_p95_ms: 250,
    reqs_per_sec: 75,
    error_rate: 0,
    checks_rate: 1,
    data_received: 1000,
    data_received_rate: 100,
  },
});

test('compare deux moteurs : previent que les mesures ne se recouvrent pas', () => {
  const runs = [
    run('a', 'locust', 'closed', { vus: 30 }, 1000),
    run('b', 'k6', 'open', { rate: 200 }, 2000),
  ];

  render(<HistoryCard runs={runs} compare={['a', 'b']} onToggle={vi.fn()} onClear={vi.fn()} />);

  expect(screen.getByText(/Deux moteurs différents/)).toBeInTheDocument();
  expect(screen.getByText(/arrondit/)).toBeInTheDocument();
  // L'avertissement generique sur les profils ferait doublon et dirait moins juste.
  expect(screen.queryByText(/Profils d'entrée différents/)).not.toBeInTheDocument();
});

test('deux runs du meme moteur gardent l avertissement sur les profils', () => {
  const runs = [
    run('a', 'locust', 'closed', { vus: 30 }, 1000),
    run('b', 'locust', 'closed', { vus: 200 }, 2000),
  ];

  render(<HistoryCard runs={runs} compare={['a', 'b']} onToggle={vi.fn()} onClear={vi.fn()} />);

  expect(screen.getByText(/Profils d'entrée différents/)).toBeInTheDocument();
  expect(screen.queryByText(/Deux moteurs différents/)).not.toBeInTheDocument();
});

test('affiche le type de charge de chaque run compare', () => {
  const runs = [
    run('a', 'locust', 'closed', { vus: 30 }, 1000),
    run('b', 'k6', 'open', { rate: 200 }, 2000),
  ];

  render(<HistoryCard runs={runs} compare={['a', 'b']} onToggle={vi.fn()} onClear={vi.fn()} />);

  expect(screen.getByText('utilisateurs → flux imposé')).toBeInTheDocument();
});

test('le rapport k6 reste ouvrable sans selectionner le run pour comparaison', () => {
  const onToggle = vi.fn();
  const passe = run('a', 'k6', 'open', { rate: 200 }, 1000);
  passe.result.report_url = '/load-report/k6_abc123.html';

  render(<HistoryCard runs={[passe]} compare={[]} onToggle={onToggle} onClear={vi.fn()} />);

  const lien = screen.getByRole('link', { name: /Rapport k6/ });
  expect(lien.getAttribute('href')).toContain('/load-report/k6_abc123.html');
  fireEvent.click(lien);
  expect(onToggle).not.toHaveBeenCalled();
});

test('un run sans rapport ne propose pas de lien mort', () => {
  const runs = [run('a', 'locust', 'closed', { vus: 30 }, 1000)];

  render(<HistoryCard runs={runs} compare={[]} onToggle={vi.fn()} onClear={vi.fn()} />);

  expect(screen.queryByRole('link', { name: /Rapport k6/ })).not.toBeInTheDocument();
});
