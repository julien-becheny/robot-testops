import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';

import LaunchPage from './LaunchPage';

const preflight = (data) => {
  global.fetch = vi.fn(async () => ({ ok: true, json: async () => data }));
};

beforeEach(() => {
  preflight({ ok: false, checks: [] });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

test('résume les combinaisons ciblées par le smoke avant de le lancer', async () => {
  const onLaunch = vi.fn();
  render(
    <LaunchPage
      kind="smoke"
      selectedBrowsers={['chromium', 'firefox']}
      selectedDevices={['desktop', 'mobile']}
      onLaunch={onLaunch}
    />
  );

  expect(screen.getByText('4 combinaisons')).toBeInTheDocument();
  expect(screen.getByText(/Chromium · Desktop/)).toBeInTheDocument();
  expect(screen.getByText(/Firefox · Mobile/)).toBeInTheDocument();

  expect(onLaunch).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: /Lancer le smoke test/ }));
  await waitFor(() => expect(onLaunch).toHaveBeenCalledTimes(1));
});

test('annonce ce que joue le run mobile', () => {
  render(<LaunchPage kind="appium" onLaunch={vi.fn()} />);

  expect(screen.getByText('Appium')).toBeInTheDocument();
  expect(screen.getByText('appium/ + multi_moteur/')).toBeInTheDocument();
});

test('affiche l’appareil réellement détecté au lieu d’un avertissement permanent', async () => {
  preflight({
    ok: true,
    appium_online: false,
    checks: [{ name: 'Appareil Android', ok: true, detail: 'emulator-5554' }],
  });

  render(<LaunchPage kind="appium" onLaunch={vi.fn()} />);

  expect(
    await screen.findByText(/Appareil emulator-5554 détecté · Appium sera démarré au lancement/)
  ).toBeInTheDocument();
});

test('détaille ce qui manque quand la chaîne mobile n’est pas prête', async () => {
  preflight({
    ok: false,
    appium_online: false,
    checks: [
      { name: 'Appareil Android', ok: false, detail: 'aucun appareil détecté', hint: 'Brancher' },
      { name: 'Driver Appium uiautomator2', ok: true, detail: 'installe' },
    ],
  });

  render(<LaunchPage kind="appium" onLaunch={vi.fn()} />);

  expect(
    await screen.findByText(/Appareil Android : aucun appareil détecté - Brancher/)
  ).toBeInTheDocument();
  // Seuls les points en echec sont listes : le reste serait du bruit.
  expect(screen.queryByText(/Driver Appium/)).not.toBeInTheDocument();
});
