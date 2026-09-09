import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, test } from 'vitest';

import { LogBlockList, groupLogs } from './logBlocks';

afterEach(cleanup);

const at = (s) => new Date(Date.UTC(2026, 0, 1, 0, 0, s)).toISOString();

const line = (text, type, s) => ({ text, type, timestamp: at(s), executionId: null });

const start = (name, s, execId) => ({
  text: `🧪 Test: ${name}`,
  type: 'test-start',
  timestamp: at(s),
  executionId: execId,
});

describe('groupLogs', () => {
  test('replie les lignes sous le test qui les précède et date la durée sur le verdict', () => {
    const { preamble, blocks } = groupLogs([
      line('Démarrage du run', 'info', 0),
      start('Connexion valide', 2, 'a'),
      line('Ouverture du navigateur', 'info', 3),
      line("✅ Le test s'est exécuté avec succès", 'success', 7),
      start('Commande complète', 8, 'b'),
      line('❌ Le test a échoué', 'error', 20),
      line('Message: locator introuvable', 'error-detail', 20),
    ]);

    expect(preamble.map((l) => l.text)).toEqual(['Démarrage du run']);
    expect(blocks).toHaveLength(2);

    expect(blocks[0].name).toBe('Connexion valide');
    expect(blocks[0].verdict).toBe('pass');
    expect(blocks[0].ms).toBe(5000);

    expect(blocks[1].verdict).toBe('fail');
    // La ligne « Message: » suit le verdict : elle ne rallonge pas la durée du test.
    expect(blocks[1].ms).toBe(12000);
    expect(blocks[1].lines).toHaveLength(2);
  });

  test('numérote les passages successifs d’un même test rejoué', () => {
    const { blocks } = groupLogs([
      start('Commande complète', 0, 'x1'),
      line('❌ Le test a échoué', 'error', 5),
      start('Commande complète', 6, 'x2'),
      line("✅ Le test s'est exécuté avec succès", 'success', 9),
    ]);

    expect(blocks.map((b) => [b.attempt, b.attempts])).toEqual([
      [1, 2],
      [2, 2],
    ]);
  });

  test('laisse le verdict vide tant que le test tourne', () => {
    const { blocks } = groupLogs([start('En cours', 0, 'y'), line('Clic', 'info', 1)]);

    expect(blocks[0].verdict).toBeNull();
    expect(blocks[0].ms).toBeNull();
  });
});

describe('LogBlockList', () => {
  const logs = [
    start('Connexion valide', 0, 'a'),
    line("✅ Le test s'est exécuté avec succès", 'success', 4),
    start('Commande complète', 5, 'b'),
    line('❌ Le test a échoué', 'error', 17),
    line('Message: locator introuvable', 'error-detail', 17),
    start('Déconnexion', 18, 'c'),
    line('Menu ouvert', 'info', 19),
  ];

  const head = (name) => screen.getByRole('button', { name: new RegExp(name) });

  test('ouvre l’échec et le test en cours, garde la réussite repliée', () => {
    render(<LogBlockList logs={logs} running />);

    expect(head('Commande complète')).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('Message: locator introuvable')).toBeInTheDocument();

    expect(head('Déconnexion')).toHaveAttribute('aria-expanded', 'true');

    expect(head('Connexion valide')).toHaveAttribute('aria-expanded', 'false');
  });

  test('referme le test en cours une fois le run terminé', () => {
    render(<LogBlockList logs={logs} running={false} />);

    expect(head('Déconnexion')).toHaveAttribute('aria-expanded', 'false');
  });

  test('un clic prime sur la règle d’ouverture par défaut', () => {
    render(<LogBlockList logs={logs} running={false} />);

    fireEvent.click(head('Commande complète'));
    expect(head('Commande complète')).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(head('Connexion valide'));
    expect(screen.getByText("✅ Le test s'est exécuté avec succès")).toBeInTheDocument();
  });
});
