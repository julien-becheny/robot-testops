const getApiBaseUrl = () => {
  // En démonstration, un backend simulé répond à la place du serveur (voir src/demo/).
  if (import.meta.env.VITE_DEMO === '1') return import.meta.env.BASE_URL.replace(/\/$/, '');
  if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
    return `http://${window.location.hostname}:5001`;
  }
  return 'http://localhost:5001';
};

export const API_BASE_URL = getApiBaseUrl();
export const SOCKET_URL = getApiBaseUrl();

/**
 * Ramène une URL forgée par le backend sur l'hôte par lequel on le joint.
 *
 * Les runners construisent les liens de leurs dashboards avec « localhost », qui
 * désigne leur propre machine. Interprété par un navigateur distant, ce nom
 * désignerait le poste de l'utilisateur : le lien tombe alors sur un refus de
 * connexion. Le port et le chemin sont conservés.
 */
export const withCurrentHost = (url, host = window.location.hostname) => {
  try {
    const cible = new URL(url);
    cible.hostname = host;
    return cible.toString();
  } catch {
    return url;
  }
};

/** Écrit une variable de configuration du backend (cible, ralenti, etc.). */
export const setConfigVar = async (key, value) => {
  try {
    await fetch(`${API_BASE_URL}/config-vars`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key, value }),
    });
  } catch (err) {
    console.error(`Erreur sync ${key}:`, err);
  }
};
