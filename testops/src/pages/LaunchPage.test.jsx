import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';

import LaunchPage from './LaunchPage';

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

test('résume les combinaisons ciblées par le smoke avant de le lancer', async () => {
  const onLaunch = vi.fn();
  render(
    <LaunchPage
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
