import { describe, expect, it, test } from 'vitest';

import { API_BASE_URL, withCurrentHost } from './api';

// Vite expose toute variable `VITE_*` de l'environnement. Celle laissée dans un terminal
// après un build de démonstration basculait l'application en mode simulé pendant les
// tests, qui tombaient alors très loin de leur cause. La configuration la neutralise.
test('les tests parlent au backend local, jamais au backend simulé', () => {
  expect(API_BASE_URL).toBe('http://localhost:5001');
});

describe('withCurrentHost', () => {
  it("remplace l'hôte du backend par celui du navigateur, port conservé", () => {
    expect(withCurrentHost('http://localhost:51349', '192.168.1.142')).toBe(
      'http://192.168.1.142:51349/'
    );
  });

  it('laisse une URL déjà servie par le bon hôte inchangée', () => {
    const url = 'http://192.168.1.142:8089/';
    expect(withCurrentHost(url, '192.168.1.142')).toBe(url);
  });

  it('conserve le chemin et la chaîne de requête', () => {
    expect(withCurrentHost('http://localhost:8089/stats?a=1', 'tour')).toBe(
      'http://tour:8089/stats?a=1'
    );
  });

  it("rend l'entrée telle quelle quand ce n'est pas une URL absolue", () => {
    expect(withCurrentHost('/load-report/k6_abc.html', 'tour')).toBe('/load-report/k6_abc.html');
  });
});
