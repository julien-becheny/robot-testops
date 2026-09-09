"""Création de l'application Flask et configuration de ses échanges cross-origin."""

from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO

from core import config

DEFAULT_ALLOWED_ORIGINS = (
	"http://localhost:3000",
	"http://127.0.0.1:3000",
)


def _allowed_origins() -> list[str]:
	"""Résout les origines web autorisées à appeler l'API TestOps.

	La configuration accepte une liste JSON ou une chaîne dont les valeurs sont
	séparées par des virgules. Une valeur absente, invalide ou vide rétablit les
	origines locales utilisées par le frontend de développement.

	Returns:
		La liste non vide des origines transmises à Flask-CORS et Socket.IO.
	"""
	configured = config.get("API_ALLOWED_ORIGINS", list(DEFAULT_ALLOWED_ORIGINS))
	if isinstance(configured, str):
		configured = configured.split(",")
	if not isinstance(configured, (list, tuple)):
		return list(DEFAULT_ALLOWED_ORIGINS)

	origins = [str(origin).strip() for origin in configured if str(origin).strip()]
	return origins or list(DEFAULT_ALLOWED_ORIGINS)

app = Flask(__name__)
allowed_origins = _allowed_origins()
CORS(app, origins=allowed_origins)
socketio = SocketIO(app, cors_allowed_origins=allowed_origins)
