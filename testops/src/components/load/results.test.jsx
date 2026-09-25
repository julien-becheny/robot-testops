import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, test } from 'vitest';

import { LiveBand, ResultCard, BreachCard } from './results';
import { BAD } from './theme';

const result = (overrides = {}) => ({
  min_ms: 101,
  p50_ms: 190,
  p95_ms: 390,
  p99_ms: 510,
  max_ms: 3916.2,
  ttfb_p95_ms: 396.5,
  error_rate: 0,
  checks_rate: 1,
  reqs_per_sec: 880,
  reqs_total: 819285,
  vus_max: 600,
  vus_target_max: 600,
  vus_deficit_pct: 0,
  data_received: 2332500000,
  data_received_rate: 2500000,
  data_sent: 0,
  thresholds_ok: true,
  status: 'ok',
  ...overrides,
});

afterEach(cleanup);

test('relegue la requete la plus lente en note secondaire au lieu d une metrique', () => {
  render(<ResultCard result={result()} />);

  expect(screen.queryByText('Max')).not.toBeInTheDocument();
  const note = screen.getByText(/Requête la plus lente du run/);
  expect(note).toHaveTextContent('3916.2 ms');
  expect(note).toHaveTextContent(/non\s+représentative/);
});

test('affiche la charge CPU de l injecteur quand elle a ete mesuree', () => {
  render(<ResultCard result={result({ injector_cpu_max: 102.2, injector_cpu_warning: true })} />);

  expect(screen.getByText('Injecteur (machine de test)')).toBeInTheDocument();
  expect(screen.getByText('102 %')).toBeInTheDocument();
});

test('montre la part du lien reseau consommee par le run', () => {
  render(<ResultCard result={result({ network_usage_pct: 82, link_speed_mbps: 100 })} />);

  expect(screen.getByText('Part du lien')).toBeInTheDocument();
  expect(screen.getByText('82 % de 100 Mb/s')).toBeInTheDocument();
});

test('consigne le parallelisme, sans lequel deux runs sont incomparables', () => {
  render(<ResultCard result={result({ injector_processes: 6, injector_cores: 6 })} />);

  expect(screen.getByText('Parallélisme')).toBeInTheDocument();
  expect(screen.getByText('6 proc. / 6 cœurs')).toBeInTheDocument();
});

test('un stress ne se solde jamais par un « Réussi »', () => {
  render(<ResultCard result={result({ test_type: 'stress', status: 'ok', p95_ms: 4400 })} />);

  expect(screen.getByText('Surcharge explorée')).toBeInTheDocument();
  expect(screen.queryByText('Réussi')).not.toBeInTheDocument();
});

test('un decrochage de debit ne parle pas d utilisateurs', () => {
  render(
    <BreachCard
      breach={{ cause: 'dropped', t: 132, rps: 13, p95_ms: 976, dropped: 6 }}
      seuil={800}
    />
  );

  expect(screen.getByText('Décrochage du débit')).toBeInTheDocument();
  expect(screen.getByText('13 req/s')).toBeInTheDocument();
  expect(screen.getByText("capacité d'absorption")).toBeInTheDocument();
  // Sans taux d'erreur transmis, la cellule disparait au lieu d'afficher un tiret.
  expect(screen.queryByText('Utilisateurs actifs')).not.toBeInTheDocument();
  expect(screen.queryByText('Erreurs')).not.toBeInTheDocument();
});

const breach = (overrides = {}) => ({
  t: 20,
  users: 50,
  p95_ms: 25,
  rps: 1797,
  error_rate: 0,
  ...overrides,
});

test('une saturation d injecteur est nommee comme telle, pas comme un seuil franchi', () => {
  render(<BreachCard breach={breach({ cause: 'cpu', cpu: 100 })} seuil={800} />);

  expect(screen.getByText("Saturation de l'injecteur")).toBeInTheDocument();
  expect(screen.getByText('CPU injecteur')).toBeInTheDocument();
  expect(screen.getByText('100 %')).toBeInTheDocument();
  expect(screen.queryByText('p95 au fail')).not.toBeInTheDocument();
});

test('une rupture sur seuil de latence garde son libelle d origine', () => {
  render(<BreachCard breach={breach()} seuil={800} />);

  expect(screen.getByText('Point de rupture')).toBeInTheDocument();
  expect(screen.getByText('p95 au fail')).toBeInTheDocument();
  expect(screen.getByText('seuil 800 ms')).toBeInTheDocument();
});

test('masque la section injecteur quand aucune mesure CPU n est disponible', () => {
  render(<ResultCard result={result({ injector_cpu_max: null })} />);

  expect(screen.queryByText('Injecteur (machine de test)')).not.toBeInTheDocument();
});

test('affiche le plancher de latence a cote des percentiles', () => {
  render(<ResultCard result={result()} />);

  expect(screen.getByText('Plancher (min)')).toBeInTheDocument();
  expect(screen.getByText('101 ms')).toBeInTheDocument();
  expect(screen.getByText('VUs demandés')).toBeInTheDocument();
});

test('signale le p99 hors seuil sans accuser le p95 qui tient', () => {
  render(
    <ResultCard
      result={result({ seuil_p95_ms: 800, seuil_p99_ms: 1600, p99_ms: 2400, status: 'fail' })}
    />
  );

  expect(screen.getByText('2400 ms')).toHaveStyle({ color: BAD });
  expect(screen.getByText('390 ms')).not.toHaveStyle({ color: BAD });
});

test('le bandeau live montre le CPU et la cible d utilisateurs', () => {
  render(<LiveBand live={{ vus: 540, vus_target: 600, vus_lagging: true, cpu: 88 }} />);

  expect(screen.getByText('540 / 600')).toBeInTheDocument();
  expect(screen.getByText('88 %')).toBeInTheDocument();
  expect(screen.getByText(/injecteur peine à suivre le plan/)).toBeInTheDocument();
});

test('le bandeau live reste lisible sans mesure CPU ni cible', () => {
  render(<LiveBand live={{ vus: 120 }} />);

  expect(screen.getByText('120')).toBeInTheDocument();
  expect(screen.getByText('CPU injecteur').nextSibling).toHaveTextContent('-');
  expect(screen.queryByText(/peine à suivre/)).not.toBeInTheDocument();
});

test('signale la charge auto-limitee a cote du debit', () => {
  render(<ResultCard result={result({ throughput_shortfall_pct: 62.4 })} />);

  expect(screen.getByText('Charge auto-limitée').nextSibling).toHaveTextContent('-62 %');
});

test('masque l auto-limitation quand elle n a pas ete mesuree', () => {
  render(<ResultCard result={result()} />);

  expect(screen.queryByText('Charge auto-limitée')).not.toBeInTheDocument();
});

test('modele ouvert : montre le debit vise et les requetes jamais parties', () => {
  render(
    <ResultCard
      result={result({
        model: 'open',
        rate_target: 200,
        dropped_iterations: 2572,
        dropped_pct: 46.8,
      })}
    />
  );

  expect(screen.getByText('Débit visé').nextSibling).toHaveTextContent('200 req/s');
  expect(screen.getByText('Non parties').nextSibling).toHaveTextContent('2572 (46.8 %)');
});

test('le bandeau live montre ensemble le CPU et les requetes non parties', () => {
  render(<LiveBand live={{ vus: 300, reqs_per_sec: 180, p95_ms: 900, dropped: 42, cpu: 64 }} />);

  // Les deux ensemble : sans le CPU, rien ne distingue un systeme lent d'un injecteur a bout.
  expect(screen.getByText('Non parties').nextSibling).toHaveTextContent('42');
  expect(screen.getByText('CPU injecteur').nextSibling).toHaveTextContent('64 %');
});
