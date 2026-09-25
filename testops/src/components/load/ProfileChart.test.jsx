import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, test } from 'vitest';

import { ProfileChart } from './ProfileChart';

afterEach(cleanup);

test('modele ferme : l axe porte des utilisateurs', () => {
  render(
    <ProfileChart
      testType="load"
      params={{ vus: 200, ramp_up: '1m30s', steady: '1m30s', ramp_down: '30s' }}
    />
  );

  expect(screen.getByText(/Profil de charge/)).toHaveTextContent('VUs dans le temps');
  expect(screen.getByText(/pic 200 VUs/)).toBeInTheDocument();
});

test('modele ouvert : l axe porte un debit', () => {
  render(
    <ProfileChart
      testType="open_load"
      params={{ rate: 150, ramp_up: '30s', steady: '1m', ramp_down: '20s' }}
    />
  );

  expect(screen.getByText(/Profil de charge/)).toHaveTextContent('req/s dans le temps');
  expect(screen.getByText(/pic 150 req\/s/)).toBeInTheDocument();
});

test('capacite en debit : les paliers se lisent dans rate_max, pas dans vus_max', () => {
  render(
    <ProfileChart
      testType="open_capacity"
      params={{ rate_start: 50, rate_max: 400, rate_step: 50, ramp: '10s', steady: '30s' }}
    />
  );

  expect(screen.getByText(/pic 400 req\/s/)).toBeInTheDocument();
});

test('endurance a debit : plateau lu dans rate et duration', () => {
  render(<ProfileChart testType="open_endurance" params={{ rate: 50, duration: '30m' }} />);

  expect(screen.getByText(/pic 50 req\/s · 30m/)).toBeInTheDocument();
});
