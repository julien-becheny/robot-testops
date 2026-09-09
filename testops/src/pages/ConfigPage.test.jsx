import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';

import ConfigPage from './ConfigPage';

const MASKED_CONFIG_VALUE = '********';

const response = (data, ok = true) => ({
  ok,
  json: async () => data,
});

const renderConfig = async () => {
  render(<ConfigPage onBack={vi.fn()} />);
  await screen.findByText('RF_PASSWORD');
};

beforeEach(() => {
  global.fetch = vi.fn().mockResolvedValue(
    response({
      RF_LOGIN: 'utilisateur',
      RF_PASSWORD: MASKED_CONFIG_VALUE,
      RF_BASE_URL: 'https://example.test',
    })
  );
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

test('affiche le login et masque le mot de passe', async () => {
  await renderConfig();

  expect(screen.getByText('utilisateur')).toBeInTheDocument();
  expect(screen.getByText('••••••')).toBeInTheDocument();
  expect(screen.queryByText(MASKED_CONFIG_VALUE)).not.toBeInTheDocument();
});

test('édite un secret dans un champ vide puis ne conserve que le masque', async () => {
  await renderConfig();
  const passwordRow = screen.getByText('RF_PASSWORD').closest('.config-row');
  const passwordRowQueries = within(passwordRow);

  fireEvent.click(passwordRowQueries.getByTitle('Modifier'));
  const passwordInput = passwordRowQueries.getByPlaceholderText('Nouvelle valeur');
  expect(passwordInput).toHaveAttribute('type', 'password');
  expect(passwordInput).toHaveValue('');

  global.fetch.mockResolvedValueOnce(response({ value: MASKED_CONFIG_VALUE }));
  fireEvent.change(passwordInput, { target: { value: 'nouvelle-valeur' } });
  fireEvent.click(passwordRowQueries.getByTitle('Enregistrer'));

  await waitFor(() => {
    expect(global.fetch).toHaveBeenCalledTimes(2);
    expect(passwordInput).toHaveValue('');
  });
  const [, options] = global.fetch.mock.calls[1];
  expect(JSON.parse(options.body)).toEqual({
    key: 'RF_PASSWORD',
    value: 'nouvelle-valeur',
  });
  expect(screen.queryByDisplayValue('nouvelle-valeur')).not.toBeInTheDocument();
});

test('efface explicitement un secret configuré', async () => {
  await renderConfig();
  global.fetch.mockResolvedValueOnce(response({ value: null }));

  fireEvent.click(screen.getByLabelText('Effacer RF_PASSWORD'));

  await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(2));
  const [, options] = global.fetch.mock.calls[1];
  expect(JSON.parse(options.body)).toEqual({ key: 'RF_PASSWORD', value: null });
  await waitFor(() => expect(screen.queryByText('••••••')).not.toBeInTheDocument());
});
