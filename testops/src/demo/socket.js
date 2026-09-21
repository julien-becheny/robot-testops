/**
 * Remplace `socket.io-client` en mode démonstration (alias déclaré dans vite.config.js).
 *
 * Le code de l'application est inchangé : il appelle `io()`, s'abonne et se
 * désabonne comme d'habitude - les événements viennent du bus local au lieu du
 * réseau.
 */
import { on, off } from './bus';

export const io = () => ({
  on,
  off,
  // L'application annonce son entrée dans une room ; sans serveur, il n'y a rien à router.
  emit: () => {},
  disconnect: () => {},
});

const client = { io };

export default client;
