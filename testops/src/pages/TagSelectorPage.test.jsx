import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';

import TagSelectorPage from './TagSelectorPage';

const CATALOG = {
  tags: [
    { name: 'saucedemo', count: 13 },
    { name: 'web', count: 12 },
    { name: 'cart', count: 4 },
  ],
};

const TESTS = [
  { name: 'Connexion réussie', file: 'test_suites/web/saucedemo/01_login.robot', tags: [] },
  { name: 'Connexion refusée', file: 'test_suites/web/saucedemo/01_login.robot', tags: [] },
  { name: 'Ajout au panier', file: 'test_suites/web/saucedemo/02_cart.robot', tags: [] },
];

const installFetch = (count = 14, tests = TESTS) => {
  global.fetch = vi.fn(async (input) => {
    const path = new URL(String(input)).pathname;
    if (path === '/available-tags') return { ok: true, json: async () => CATALOG };
    if (path === '/matching-tests') return { ok: true, json: async () => ({ count, tests }) };
    return { ok: true, json: async () => ({}) };
  });
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const includePanel = () => within(screen.getByRole('region', { name: 'Tags à inclure' }));
const hero = () => within(screen.getByRole('region', { name: 'Périmètre du run' }));
const preview = () => within(screen.getByRole('region', { name: 'Tests correspondants' }));

test('propose des tags sans les sélectionner à la place de l’utilisateur', async () => {
  installFetch();
  const onRunByTags = vi.fn();

  render(<TagSelectorPage onRunByTags={onRunByTags} />);

  // La suggestion est visible, mais rien n'est encore choisi.
  await waitFor(() => expect(screen.getAllByText('Aucun tag inclus').length).toBe(1));
  const suggestion = includePanel().getByRole('button', { name: /saucedemo 13/ });

  fireEvent.click(suggestion);
  fireEvent.click(screen.getByRole('button', { name: /Lancer l’exécution/ }));

  await waitFor(() => expect(onRunByTags).toHaveBeenCalledWith(['saucedemo'], [], false, false, 0));
});

test('garde les tags proposés à portée de clic après un premier choix', async () => {
  installFetch();

  render(<TagSelectorPage onRunByTags={vi.fn()} />);
  const panel = includePanel();
  fireEvent.click(await panel.findByRole('button', { name: /saucedemo 13/ }));

  // Le tag choisi quitte les propositions, les autres restent offerts.
  expect(panel.queryByRole('button', { name: /saucedemo 13/ })).not.toBeInTheDocument();
  expect(panel.getByRole('button', { name: /web 12/ })).toBeInTheDocument();
});

test('l’aléatoire entraîne le rejeu des échecs, et l’explique', async () => {
  installFetch();
  const onRunByTags = vi.fn();

  render(<TagSelectorPage onRunByTags={onRunByTags} />);
  await waitFor(() => expect(includePanel().getByText('saucedemo')).toBeInTheDocument());

  const random = screen.getByLabelText('Exécution aléatoire');
  const rerun = screen.getByLabelText('Rejouer les échecs');
  expect(rerun).not.toBeChecked();

  fireEvent.click(random);

  expect(rerun).toBeChecked();
  expect(screen.getByText(/un échec peut venir de l’ordre/)).toBeInTheDocument();
});

test('annonce le nombre réellement lancé, distinct du nombre correspondant', async () => {
  installFetch(100);

  render(<TagSelectorPage onRunByTags={vi.fn()} />);
  await waitFor(() => expect(hero().getByText('100')).toBeInTheDocument());
  expect(hero().getByText(/tests correspondent aux tags choisis/)).toBeInTheDocument();

  fireEvent.click(screen.getByLabelText('Exécution aléatoire'));
  fireEvent.change(screen.getByLabelText('Nombre de tests à sélectionner'), {
    target: { value: '10' },
  });

  expect(hero().getByText('10')).toBeInTheDocument();
  expect(hero().getByText(/tirés au sort parmi les 100 correspondants/)).toBeInTheDocument();
});

test('montre les tests que le run va jouer, groupés par suite', async () => {
  installFetch(3);

  render(<TagSelectorPage onRunByTags={vi.fn()} />);

  await waitFor(() => expect(preview().getByText('Connexion réussie')).toBeInTheDocument());
  expect(preview().getByText('Ajout au panier')).toBeInTheDocument();
  expect(preview().getByText('web/saucedemo/01_login.robot')).toBeInTheDocument();
  expect(preview().getByText('web/saucedemo/02_cart.robot')).toBeInTheDocument();
});

test('prévient que le tirage au sort ne jouera pas toute la liste montrée', async () => {
  installFetch(3);

  render(<TagSelectorPage onRunByTags={vi.fn()} />);
  await waitFor(() => expect(preview().getByText('Connexion réussie')).toBeInTheDocument());

  fireEvent.click(screen.getByLabelText('Exécution aléatoire'));
  fireEvent.change(screen.getByLabelText('Nombre de tests à sélectionner'), {
    target: { value: '2' },
  });

  expect(preview().getByText(/2 tests seront tirés au sort parmi ceux-ci/)).toBeInTheDocument();
});

test('choisit un tag au clavier depuis la liste déroulante', async () => {
  installFetch();

  render(<TagSelectorPage onRunByTags={vi.fn()} />);
  const search = await screen.findByRole('combobox', { name: 'Tags à inclure' });

  fireEvent.click(search);
  expect(search).toHaveAttribute('aria-expanded', 'true');

  fireEvent.keyDown(search, { key: 'ArrowDown' });
  fireEvent.keyDown(search, { key: 'Enter' });

  expect(includePanel().getByText('saucedemo')).toBeInTheDocument();
  expect(screen.queryByText('Aucun tag inclus')).not.toBeInTheDocument();
});

test('n’offre pas de lancer un run vide', async () => {
  installFetch(0, []);

  render(<TagSelectorPage onRunByTags={vi.fn()} />);

  await waitFor(() =>
    expect(screen.getByRole('button', { name: /Lancer l’exécution/ })).toBeDisabled()
  );
  expect(hero().getByText('Aucun test ne correspond à ces critères.')).toBeInTheDocument();
  expect(preview().getByText('Aucun test ne correspond à ces critères.')).toBeInTheDocument();
});
