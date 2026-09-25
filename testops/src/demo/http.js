/**
 * Réponses HTTP du backend simulé, et le filtre par tags qu'elles partagent.
 */
import fixtures from './fixtures.json';

export const json = (body, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

/** Les tests du catalogue enregistré retenus par un filtre, comme `/matching-tests`. */
export const matching = (include = [], exclude = []) =>
  fixtures.tests.filter((test) => {
    const tags = test.tags || [];
    if (exclude.some((tag) => tags.includes(tag))) return false;
    return include.length === 0 || include.some((tag) => tags.includes(tag));
  });
