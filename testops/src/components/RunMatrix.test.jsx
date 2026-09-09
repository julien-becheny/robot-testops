import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, test } from 'vitest';

import RunMatrix from './RunMatrix';

const sessions = [
  { sessionId: 'a', browser: 'chromium-desktop', completed: true },
  { sessionId: 'b', browser: 'firefox-mobile', completed: true },
];

const verdict = (name, status) => ({ name, status, message: '' });

afterEach(cleanup);

test('range les tests en ligne et les configurations en colonne', () => {
  render(
    <RunMatrix
      sessions={sessions}
      results={{
        a: { 'Suite.Panier': verdict('Panier', 'PASS') },
        b: { 'Suite.Panier': verdict('Panier', 'PASS') },
      }}
    />
  );

  expect(screen.getByRole('columnheader', { name: 'chromium-desktop' })).toBeInTheDocument();
  expect(screen.getByRole('columnheader', { name: 'firefox-mobile' })).toBeInTheDocument();
  expect(screen.getByTitle('Panier · chromium-desktop : Réussi')).toBeInTheDocument();
  expect(screen.getByTitle('Panier · firefox-mobile : Réussi')).toBeInTheDocument();
});

test('signale la ligne où les configurations ne sont pas d’accord', () => {
  render(
    <RunMatrix
      sessions={sessions}
      results={{
        a: { 'Suite.Panier': verdict('Panier', 'PASS'), 'Suite.Login': verdict('Login', 'PASS') },
        b: { 'Suite.Panier': verdict('Panier', 'FAIL'), 'Suite.Login': verdict('Login', 'PASS') },
      }}
    />
  );

  expect(screen.getByTitle('Suite.Panier').closest('tr')).toHaveClass('diverging');
  expect(screen.getByTitle('Suite.Login').closest('tr')).not.toHaveClass('diverging');
});

test('ne confond pas un test non joué avec un test réussi', () => {
  render(
    <RunMatrix
      sessions={sessions}
      results={{ a: { 'Suite.Panier': verdict('Panier', 'PASS') }, b: {} }}
    />
  );

  expect(screen.getByTitle('Panier · firefox-mobile : Non joué')).toBeInTheDocument();
});

test('distingue une configuration encore en cours d’une configuration terminée', () => {
  render(
    <RunMatrix
      sessions={[sessions[0], { ...sessions[1], completed: false }]}
      results={{ a: { 'Suite.Panier': verdict('Panier', 'PASS') }, b: {} }}
    />
  );

  expect(screen.getByTitle('Panier · firefox-mobile : En attente')).toBeInTheDocument();
});

test('reste lisible tant qu’aucun test n’est terminé', () => {
  render(<RunMatrix sessions={sessions} results={{}} />);

  expect(screen.getByText(/Aucun test terminé/)).toBeInTheDocument();
});
