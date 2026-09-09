const getApiBaseUrl = () => {
  if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
    return `http://${window.location.hostname}:5001`;
  }
  return 'http://localhost:5001';
};

export const API_BASE_URL = getApiBaseUrl();
export const SOCKET_URL = getApiBaseUrl();

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
