import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import Header from './Header';

const response = (data) => ({ ok: true, json: async () => data });

const installFetch = (environments, configVars = {}) => {
  global.fetch = vi.fn(async (input) => {
    const path = new URL(String(input)).pathname;
    if (path === '/git-info') return response({ branch: 'main' });
    if (path === '/config-vars') return response({ RF_SLOW_MO: '0:00:00', ...configVars });
    if (path === '/environments') return response(environments);
    return response({});
  });
};

const SINGLE_ENV = {
  active: 'recette',
  environments: [
    { id: 'recette', label: 'Recette', base: 'https://recette.client.fr', modules: ['travaux'] },
  ],
};

const TWO_ENVS = {
  active: 'preprod',
  environments: [
    { id: 'recette', label: 'Recette', base: 'https://recette.client.fr', modules: ['travaux'] },
    { id: 'preprod', label: 'Préprod', base: 'https://preprod.client.fr', modules: ['travaux'] },
  ],
};

const findRequest = (path, method) =>
  global.fetch.mock.calls.find(
    ([input, options]) => new URL(String(input)).pathname === path && options?.method === method
  );

// Tout le contexte d'un run vit derrière un déclencheur unique.
const openContext = async () =>
  fireEvent.click(await screen.findByRole('button', { name: 'Contexte des prochains runs' }));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

test('résume le contexte du prochain run sans qu’il faille ouvrir le panneau', async () => {
  installFetch(TWO_ENVS);

  render(<Header selectedBrowsers={['chromium', 'firefox']} selectedDevices={['desktop']} />);

  const trigger = await screen.findByRole('button', { name: 'Contexte des prochains runs' });
  expect(trigger).toHaveTextContent('Préprod');
  // Deux navigateurs sur un appareil : la combinatoire s'annonce avant le lancement.
  expect(trigger).toHaveTextContent('2 sessions');
});

test('propose les environnements déclarés et retient celui qui est actif', async () => {
  installFetch(TWO_ENVS);

  render(<Header />);
  await openContext();

  expect(screen.getByRole('button', { name: 'Préprod' })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByRole('button', { name: 'Recette' })).toHaveAttribute('aria-pressed', 'false');
});

test('changer d’environnement enregistre la cible du prochain run', async () => {
  installFetch({ ...TWO_ENVS, active: 'recette' });

  render(<Header />);
  await openContext();
  fireEvent.click(screen.getByRole('button', { name: 'Préprod' }));

  await waitFor(() => expect(findRequest('/config-vars', 'POST')).toBeTruthy());
  const [, options] = findRequest('/config-vars', 'POST');
  expect(JSON.parse(options.body)).toEqual({ key: 'RF_ENVIRONMENT', value: 'preprod' });
});

test('signale un référentiel vide plutôt que de laisser choisir une cible inexistante', async () => {
  installFetch({ active: null, environments: [] });

  render(<Header />);

  expect(await screen.findByText('Aucun environnement déclaré')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Contexte des prochains runs' })).toBeDisabled();
});

test('garde au moins un navigateur : un run sans navigateur n’existe pas', async () => {
  installFetch(SINGLE_ENV);
  const onBrowsersChange = vi.fn();

  render(<Header selectedBrowsers={['chromium']} onBrowsersChange={onBrowsersChange} />);
  await openContext();
  fireEvent.click(screen.getByRole('button', { name: 'Chromium' }));

  expect(onBrowsersChange).toHaveBeenCalledWith(['chromium']);
});

test('activer la trace enregistre le réglage pour les prochains runs', async () => {
  installFetch(SINGLE_ENV);

  render(<Header />);
  await openContext();
  fireEvent.click(screen.getByRole('button', { name: 'Activée' }));

  await waitFor(() => expect(findRequest('/config-vars', 'POST')).toBeTruthy());
  const [, options] = findRequest('/config-vars', 'POST');
  expect(JSON.parse(options.body)).toEqual({ key: 'RF_TRACING', value: 'on' });
});

test('montre la trace déjà active, pour ne pas la croire éteinte', async () => {
  installFetch(SINGLE_ENV, { RF_TRACING: 'on' });

  render(<Header />);
  await openContext();

  expect(screen.getByRole('button', { name: 'Activée' })).toHaveClass('active');
});
