import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';

import MenuPage from './HomePage';

const response = (data) => ({ ok: true, json: async () => data });

const installFetch = (byPath = {}) => {
  global.fetch = vi.fn(async (input) => {
    const path = new URL(String(input)).pathname;
    return path in byPath ? response(byPath[path]) : response({});
  });
};

const ENV = {
  id: 'recette',
  label: 'Recette',
  base: 'https://recette.client.fr',
  tier: 'recette',
  modules: ['travaux', 'stock'],
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

test('annonce le volume du catalogue dans le bloc qui y mène', async () => {
  installFetch({ '/available-tags': { total_tests: 23, total_tags: 14 } });

  render(<MenuPage setPage={vi.fn()} environmentStatus="ready" environment={ENV} />);

  expect(await screen.findByText('23 tests · 14 tags')).toBeInTheDocument();
});

test('attend que le backend réponde avant d’interroger le catalogue', () => {
  installFetch();

  render(<MenuPage setPage={vi.fn()} environmentStatus="loading" />);

  expect(global.fetch).not.toHaveBeenCalled();
  expect(screen.getByText('catalogue en lecture')).toBeInTheDocument();
});

test('lance le smoke depuis son bloc, en annonçant ce qui va tourner', async () => {
  installFetch({
    '/smoke-suite': { file: '00_smoke.robot', tests: ['Smoke - Titre', 'Smoke - Formulaire'] },
  });
  const onLaunchSmoke = vi.fn();

  render(<MenuPage setPage={vi.fn()} onLaunchSmoke={onLaunchSmoke} environmentStatus="ready" />);

  expect(await screen.findByText('Smoke - Titre')).toBeInTheDocument();
  expect(screen.getByText('Smoke - Formulaire')).toBeInTheDocument();
  expect(screen.getByText('Suite fixe · 00_smoke.robot')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /Lancer le smoke/ }));
  await waitFor(() => expect(onLaunchSmoke).toHaveBeenCalledTimes(1));
});

test('mène à la sélection par tags, vierge ou pré-remplie par le tag cliqué', async () => {
  installFetch({
    '/available-tags': {
      total_tests: 14,
      total_tags: 2,
      tags: [
        { name: 'saucedemo', count: 14 },
        { name: 'smoke', count: 2 },
      ],
    },
  });
  const onOpenTags = vi.fn();

  render(<MenuPage setPage={vi.fn()} onOpenTags={onOpenTags} environmentStatus="ready" />);

  fireEvent.click(await screen.findByRole('button', { name: /saucedemo/ }));
  expect(onOpenTags).toHaveBeenCalledWith(['saucedemo']);

  fireEvent.click(screen.getByRole('button', { name: /Choisir les tags/ }));
  await waitFor(() => expect(onOpenTags).toHaveBeenLastCalledWith([]));
});

test('bascule sur l’exécution en cours au lieu de proposer un lancement', () => {
  installFetch();
  const setPage = vi.fn();

  render(<MenuPage setPage={setPage} runningCount={2} />);

  expect(screen.getByText('Exécution en cours')).toBeInTheDocument();
  expect(screen.getByText('2 runs en cours')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Lancer le smoke/ })).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /Voir l’exécution/ }));
  expect(setPage).toHaveBeenCalledWith('execution');
});
