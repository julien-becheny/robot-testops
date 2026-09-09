import { expect, test } from 'vitest';

import { API_BASE_URL } from './api';

// Vite expose toute variable `VITE_*` de l'environnement. Celle laissée dans un terminal
// après un build de démonstration basculait l'application en mode simulé pendant les
// tests, qui tombaient alors très loin de leur cause. La configuration la neutralise.
test('les tests parlent au backend local, jamais au backend simulé', () => {
  expect(API_BASE_URL).toBe('http://localhost:5001');
});
