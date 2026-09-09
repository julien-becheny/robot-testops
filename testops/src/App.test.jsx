import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';

import App from './App';
import TestInProgress from './pages/ExecutionPage';

const socket = vi.hoisted(() => ({
  disconnect: vi.fn(),
  emit: vi.fn(),
  off: vi.fn(),
  on: vi.fn(),
}));

vi.mock('socket.io-client', () => ({
  io: vi.fn(() => socket),
}));

const response = (data, ok = true) => ({
  ok,
  json: async () => data,
});

const baseResponse = (path) => {
  if (path === '/git-info') return response({ branch: 'main' });
  if (path === '/config-vars') return response({ RF_SLOW_MO: '0:00:00' });
  if (path === '/environments') {
    return response({
      active: 'saucedemo',
      environments: [
        {
          id: 'saucedemo',
          label: 'SauceDemo',
          base: 'https://example.test',
          modules: ['saucedemo'],
        },
      ],
    });
  }
  return null;
};

const installFetch = (handler) => {
  global.fetch = vi.fn(async (input, options = {}) => {
    const path = new URL(String(input)).pathname;
    return handler(path, options) || baseResponse(path) || response({});
  });
};

const findRequest = (path) =>
  global.fetch.mock.calls.find(([input]) => new URL(String(input)).pathname === path);

const findSocketHandler = (eventName) =>
  socket.on.mock.calls.find(([event]) => event === eventName)?.[1];

// Le contexte de run vit derriere un declencheur unique : il faut l'ouvrir pour regler.
const openContext = async () => {
  fireEvent.click(await screen.findByRole('button', { name: 'Contexte des prochains runs' }));
};

// Le smoke ne part plus au clic du menu : on ouvre son panneau puis on lance.
const launchSmoke = async () => {
  fireEvent.click(await screen.findByRole('button', { name: 'Smoke test' }));
  fireEvent.click(await screen.findByRole('button', { name: /Lancer le smoke test/ }));
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

test('affiche la config du header dès que le backend répond, même démarré après l’interface', async () => {
  vi.useFakeTimers();
  let backendUp = false;
  installFetch((path) => {
    if (
      !backendUp &&
      (path === '/git-info' || path === '/config-vars' || path === '/environments')
    ) {
      throw new TypeError('Failed to fetch');
    }
    return null;
  });

  render(<App />);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
  // Le declencheur attend la configuration : il le dit plutot que d'afficher un vide.
  expect(screen.getByText('Chargement…')).toBeInTheDocument();

  backendUp = true;
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });

  expect(screen.getByRole('button', { name: 'Contexte des prochains runs' })).toHaveTextContent(
    'SauceDemo'
  );
  expect(screen.getByText('main')).toBeInTheDocument();
});

test('signale une API injoignable plutôt qu’une cible non configurée', async () => {
  vi.useFakeTimers();
  installFetch((path) => {
    if (path === '/git-info' || path === '/config-vars' || path === '/environments') {
      throw new TypeError('Failed to fetch');
    }
    return null;
  });

  render(<App />);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(30_000);
  });

  expect(screen.getByText('API injoignable')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Contexte des prochains runs' })).toBeDisabled();
});

test('signale un référentiel vide quand le backend ne déclare aucun environnement', async () => {
  installFetch((path) => {
    if (path === '/environments') return response({ active: null, environments: [] });
    return null;
  });

  render(<App />);

  expect(await screen.findByText('Aucun environnement déclaré')).toBeInTheDocument();
});

test('lance un smoke avec le navigateur et le viewport sélectionnés', async () => {
  installFetch((path) => {
    if (path === '/run-test') return response({ session_id: 'session-smoke' });
    return null;
  });

  render(<App />);
  await launchSmoke();

  await screen.findByText('session-smoke');
  const [, options] = findRequest('/run-test');
  expect(options).toMatchObject({
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  expect(JSON.parse(options.body)).toEqual({
    workflow: 'smoke',
    browser: 'chromium',
    viewport: '1920x1080',
  });
  expect(socket.emit).toHaveBeenCalledWith('join_session', { session_id: 'session-smoke' });
});

const PROD = {
  active: 'prod',
  environments: [
    {
      id: 'prod',
      label: 'Production client',
      base: 'https://client.fr',
      tier: 'prod',
      modules: ['travaux'],
    },
  ],
};

const launchSmokeOnProduction = async (answer) => {
  installFetch((path) => {
    if (path === '/environments') return response(PROD);
    if (path === '/run-test') return response({ session_id: 'session-prod' });
    return null;
  });
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(answer);

  render(<App />);
  await screen.findByText('Production client');
  await launchSmoke();
  await waitFor(() => expect(confirm).toHaveBeenCalled());

  return confirm;
};

test('ne lance rien sur la production tant que le lancement n’est pas confirmé', async () => {
  const confirm = await launchSmokeOnProduction(false);

  expect(confirm).toHaveBeenCalledTimes(1);
  expect(findRequest('/run-test')).toBeUndefined();
});

test('lance sur la production une fois le lancement confirmé', async () => {
  await launchSmokeOnProduction(true);

  await waitFor(() => expect(findRequest('/run-test')).toBeTruthy());
});

test('affiche le refus HTTP pour la cible sans créer de session', async () => {
  installFetch((path) => {
    if (path === '/run-test') return response({ error: 'Workflow refusé' }, false);
    return null;
  });

  render(<App />);
  await launchSmoke();

  expect(await screen.findByRole('alert')).toHaveTextContent('chromium-desktop');
  expect(screen.getByRole('alert')).toHaveTextContent('Workflow refusé');
  expect(screen.queryByText('session-smoke')).not.toBeInTheDocument();
  expect(socket.emit).not.toHaveBeenCalledWith('join_session', expect.anything());
});

test('affiche une erreur claire quand l’API de lancement est inaccessible', async () => {
  const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
  installFetch((path) => {
    if (path === '/run-test') throw new TypeError('Failed to fetch');
    return null;
  });

  render(<App />);
  await launchSmoke();

  expect(await screen.findByRole('alert')).toHaveTextContent('chromium-desktop');
  expect(screen.getByRole('alert')).toHaveTextContent("Impossible de joindre l'API TestOps");
  expect(consoleError).toHaveBeenCalled();
});

test('conserve la session réussie quand une autre cible échoue', async () => {
  installFetch((path, options) => {
    if (path !== '/run-test') return null;
    const body = JSON.parse(options.body);
    return body.browser === 'chromium'
      ? response({ error: 'Chromium indisponible' }, false)
      : response({ session_id: 'session-firefox' });
  });

  render(<App />);
  await openContext();
  fireEvent.click(screen.getByRole('button', { name: 'Firefox' }));
  await launchSmoke();

  expect(await screen.findByRole('alert')).toHaveTextContent('Chromium indisponible');
  await screen.findByText('session-firefox');
  expect(socket.emit).toHaveBeenCalledWith('join_session', { session_id: 'session-firefox' });
});

const runWithFinalStatus = async (status) => {
  installFetch((path) => {
    if (path === '/run-test') return response({ session_id: 'session-verdict' });
    return null;
  });

  render(<App />);
  await launchSmoke();
  await screen.findByText('session-verdict');

  act(() => findSocketHandler('final-status')({ session_id: 'session-verdict', ...status }));
  act(() => findSocketHandler('execution-complete')({ session_id: 'session-verdict' }));
};

test('affiche l’avancement du run, pas seulement un chrono', async () => {
  installFetch((path) => {
    if (path === '/run-test') return response({ session_id: 'session-progress' });
    return null;
  });

  render(<App />);
  await launchSmoke();
  await screen.findByText('session-progress');

  act(() => findSocketHandler('progress')({ session_id: 'session-progress', done: 1, total: 3 }));

  expect(await screen.findByText('1/3 tests')).toBeInTheDocument();
});

test('le contexte affiché reste celui du lancement, même si la barre change', async () => {
  installFetch((path) => {
    if (path === '/run-test') return response({ session_id: 'session-ctx' });
    return null;
  });

  render(<App />);
  await launchSmoke();
  await screen.findByText('session-ctx');

  const ctx = () => within(document.querySelector('.run-context'));
  expect(ctx().getByText('Chromium')).toBeInTheDocument();

  // La barre du haut change de navigateur pendant que le run tourne.
  await openContext();
  fireEvent.click(screen.getByRole('button', { name: 'Firefox' }));

  expect(ctx().getByText('Chromium')).toBeInTheDocument();
  expect(ctx().queryByText('Firefox')).not.toBeInTheDocument();
});

test('un run interrompu ne se présente pas comme un run terminé', async () => {
  installFetch((path) => {
    if (path === '/run-test') return response({ session_id: 'session-stop' });
    if (path === '/stop-test') return response({ status: 'stop_requested' });
    return null;
  });

  render(<App />);
  await launchSmoke();
  await screen.findByText('session-stop');

  fireEvent.click(screen.getByRole('button', { name: /Arrêter/ }));
  // L'arret est demande avant que le run se termine : sinon on testerait une fin normale.
  expect(await screen.findByText('Arrêt en cours…')).toBeInTheDocument();
  act(() => findSocketHandler('execution-complete')({ session_id: 'session-stop' }));

  expect(await screen.findByText('Exécution interrompue')).toBeInTheDocument();
  expect(document.querySelector('.status-card')).toHaveClass('status-warned');
});

test('un run sans échec reste vert, même quand le résumé parle d’« échoués »', async () => {
  await runWithFinalStatus({
    status: '3 tests : 3 passés, 0 échoués',
    passed: 3,
    failed: 0,
    total: 3,
  });

  expect(await screen.findByText('3 tests · 3 passés')).toBeInTheDocument();
  expect(document.querySelector('.status-card')).toHaveClass('status-success');
});

test('un test passé au rejeu n’est pas annoncé comme un succès franc', async () => {
  await runWithFinalStatus({
    status: '3 tests : 3 passés, 0 échoués',
    passed: 3,
    failed: 0,
    total: 3,
    rerun: 1,
    is_merged: true,
  });

  expect(await screen.findByText('dont 1 passé au rejeu')).toBeInTheDocument();
  expect(document.querySelector('.status-card')).toHaveClass('status-warned');
});

test('termine uniquement la session ciblée à réception de execution-complete', async () => {
  installFetch((path) => {
    if (path === '/run-test') return response({ session_id: 'session-complete' });
    return null;
  });

  render(<App />);
  await launchSmoke();
  await screen.findByText('session-complete');

  const complete = findSocketHandler('execution-complete');
  expect(complete).toBeTypeOf('function');
  act(() => complete({ session_id: 'other-session' }));
  expect(screen.getByRole('button', { name: /Arrêter/ })).toBeInTheDocument();

  act(() => complete({ session_id: 'session-complete' }));
  await screen.findByRole('button', { name: /Relancer/ });
  expect(screen.queryByRole('button', { name: /Arrêter/ })).not.toBeInTheDocument();
  expect(screen.getByText('Exécution terminée')).toBeInTheDocument();
});

test('conserve les logs et le chrono quand on quitte la page d’exécution et qu’on y revient', async () => {
  installFetch((path) => {
    if (path === '/run-test') return response({ session_id: 'session-keepalive' });
    return null;
  });

  render(<App />);
  await launchSmoke();
  await screen.findByText('session-keepalive');

  const log = findSocketHandler('log');
  act(() => log({ session_id: 'session-keepalive', message: '🧪 Test: Ouverture du navigateur' }));
  const ligne = await screen.findByText(/Ouverture du navigateur/);

  fireEvent.click(screen.getByRole('button', { name: 'Configuration' }));
  // Le masquage passe par un re-rendu : l'attendre, sinon l'assertion juge un etat transitoire.
  await waitFor(() => expect(ligne).not.toBeVisible());

  fireEvent.click(screen.getByRole('button', { name: '1 run en cours' }));
  await waitFor(() => expect(ligne).toBeVisible());
  // Le meme noeud reapparait : la page n'a pas ete remontee, rien n'a ete perdu.
  expect(screen.getByText(/Ouverture du navigateur/)).toBe(ligne);
});

test('arrête uniquement la session demandée', async () => {
  installFetch((path) => {
    if (path === '/stop-test') return response({ status: 'ok' });
    return null;
  });

  render(
    <TestInProgress
      setPage={vi.fn()}
      lastTestFunction={null}
      activeSessions={[
        {
          sessionId: 'session-stop',
          browser: 'chromium-desktop',
          workflow: 'smoke',
          completed: false,
        },
      ]}
      onSessionComplete={vi.fn()}
      onClearSessions={vi.fn()}
    />
  );

  fireEvent.click(await screen.findByRole('button', { name: /Arrêter/ }));

  await waitFor(() => expect(findRequest('/stop-test')).toBeTruthy());
  const [, options] = findRequest('/stop-test');
  expect(options.method).toBe('POST');
  expect(JSON.parse(options.body)).toEqual({ session_id: 'session-stop' });
});
