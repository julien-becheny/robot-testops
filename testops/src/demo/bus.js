/**
 * Bus d'événements minimal, partagé par le faux socket et le faux backend.
 *
 * En démonstration, personne n'écoute au bout d'un réseau : le backend simulé
 * publie ici, et le module qui remplace `socket.io-client` s'y abonne.
 */
const handlers = new Map();

export const on = (event, fn) => {
  if (!handlers.has(event)) handlers.set(event, new Set());
  handlers.get(event).add(fn);
};

export const off = (event, fn) => {
  handlers.get(event)?.delete(fn);
};

export const emit = (event, payload) => {
  handlers.get(event)?.forEach((fn) => fn(payload));
};
