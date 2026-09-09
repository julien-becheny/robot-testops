import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';

import AppShell from './AppShell';

// Le header interroge le backend : il n'est pas le sujet de ces tests.
vi.mock('./Header', () => ({
  default: () => <div data-testid="header" />,
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const renderShell = (props = {}) =>
  render(
    <AppShell currentPage="home" onNavigate={vi.fn()} {...props}>
      <p>contenu</p>
    </AppShell>
  );

test('affiche les sections de navigation et le contenu de la page', () => {
  renderShell();

  expect(screen.getByRole('navigation', { name: 'Navigation principale' })).toBeInTheDocument();
  expect(screen.getByText('Exécuter')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Exécution par tags' })).toBeInTheDocument();
  expect(screen.getByText('contenu')).toBeInTheDocument();
});

test("signale l'entrée courante et notifie la navigation au clic", () => {
  const onNavigate = vi.fn();
  renderShell({ currentPage: 'tags', onNavigate });

  expect(screen.getByRole('button', { name: 'Exécution par tags' })).toHaveAttribute(
    'aria-current',
    'page'
  );
  expect(screen.getByRole('button', { name: 'Configuration' })).not.toHaveAttribute('aria-current');

  fireEvent.click(screen.getByRole('button', { name: 'Configuration' }));
  expect(onNavigate).toHaveBeenCalledWith('config');
});

test('masque le raccourci exécution tant qu’aucune session n’existe', () => {
  renderShell({ runningCount: 0, sessionCount: 0 });

  expect(screen.queryByRole('button', { name: 'Dernière exécution' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /runs? en cours/ })).not.toBeInTheDocument();
});

test('compte les runs en cours et ouvre la page exécution', () => {
  const onNavigate = vi.fn();
  renderShell({ sessionCount: 3, runningCount: 2, onNavigate });

  fireEvent.click(screen.getByRole('button', { name: '2 runs en cours' }));
  expect(onNavigate).toHaveBeenCalledWith('execution');
});

test('bascule sur la dernière exécution quand plus rien ne tourne', () => {
  renderShell({ sessionCount: 2, runningCount: 0 });

  expect(screen.getByRole('button', { name: 'Dernière exécution' })).toBeInTheDocument();
});

test('replie et déplie le rail', () => {
  renderShell();

  fireEvent.click(screen.getByRole('button', { name: 'Replier le menu' }));
  expect(screen.getByRole('button', { name: 'Déplier le menu' })).toBeInTheDocument();
});
