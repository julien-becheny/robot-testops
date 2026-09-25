"""
Gestion de la configuration globale du projet.

Ce module centralise :
- Chargement/sauvegarde de variables_config.json
- Accès aux variables de configuration
- Validation de la configuration
"""

import json
import tempfile
from pathlib import Path
from typing import Any

from core.logging_config import configure_logging, get_logger
from core.paths import paths

configure_logging()
logger = get_logger(__name__)

_MISSING = object()
SENSITIVE_KEY_MARKERS = ("PASSWORD", "PASSWD", "SECRET", "TOKEN", "API_KEY", "APIKEY")
MASKED_CONFIG_VALUE = "********"
EXTRA_EDITABLE_KEYS = frozenset({"RF_SLOW_MO", "RF_VIEWPORT", "RF_TRACING"})


def _default_config() -> dict[str, Any]:
    """Construit une configuration locale sûre pour un premier démarrage.

    Returns:
        Un nouveau dictionnaire indépendant contenant les valeurs par défaut.
    """
    return {
        "RF_BROWSER": "chromium",
        # Environnement cible : identifiant declare dans config/environments.yaml.
        "RF_ENVIRONMENT": "saucedemo",
        # Mot de passe des comptes SauceDemo : credential public documente par le site.
        "RF_SECRET_SAUCEDEMO": "secret_sauce",  # pragma: allowlist secret
        "RF_EXECUTION_MODE": "standard",
        "RF_MOBILE_PLATFORM": "Android",
        "RF_APPIUM_URL": "http://127.0.0.1:4723",
        "RF_ANDROID_APP": None,
        "RF_ANDROID_PACKAGE": None,
        "RF_ANDROID_ACTIVITY": None,
        "RF_IOS_UDID": None,
        "RF_IOS_BUNDLE_ID": None,
        "API_HOST": "127.0.0.1",
        "API_PORT": "5001",
        "LOG_LEVEL": "INFO",
        "API_ALLOWED_ORIGINS": [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
    }


def _is_sensitive_key(key: str) -> bool:
    """Indique si le nom d'une variable désigne vraisemblablement un secret."""
    normalized_key = key.upper()
    return any(marker in normalized_key for marker in SENSITIVE_KEY_MARKERS)


class Config:
    """
    Gestionnaire de configuration centralisé.
    
    Hiérarchie de résolution des variables :
    1. Fichier JSON (config/variables_config.json)
    2. Valeur par défaut (si fournie)
    
    Usage:
        from core import config
        
        # Lecture
        env = config.get('RF_WRK_ENVT')
        
        # Écriture (sauvegardé dans JSON)
        config.set('RF_WRK_ENVT', 'staging')
    """
    
    _instance = None
    _initialized = False
    # Vrai quand le fichier existe mais n'a pas pu être lu : il ne doit plus être réécrit.
    _unreadable = False

    def __new__(cls):
        """Retourne l'unique gestionnaire de configuration du processus."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialise le singleton et charge une seule fois le fichier JSON."""
        if self._initialized:
            return
        
        self.config_file = paths.CONFIG / "variables_config.json"
        
        # _config_vars : dict interne de configuration
        self._config_vars: dict[str, Any] = {}
        
        # Charger la configuration au démarrage
        self._load_config()
        configure_logging(self.get("LOG_LEVEL", "INFO"))
        
        self._initialized = True
    
    def _load_config(self) -> None:
        """Charge le fichier JSON ou utilise les valeurs locales sûres.

        Si le fichier n'existe pas, il est créé avec les valeurs par défaut. Un
        fichier illisible, mal formé ou dont la racine n'est pas un objet JSON
        est conservé sur disque pour diagnostic, les valeurs par défaut sont
        utilisées en mémoire, et aucune sauvegarde ne le remplace jusqu'au
        prochain chargement réussi.
        """
        self._unreadable = False
        if not self.config_file.exists():
            logger.warning("Fichier de configuration introuvable : %s", self.config_file)
            self._config_vars = _default_config()
            if self._save_config():
                logger.info("Fichier de configuration par défaut créé")
            return

        try:
            # Sur les octets, json détecte seul le BOM UTF-8 et l'UTF-16 de PowerShell 5.
            loaded_data = json.loads(self.config_file.read_bytes())
        except json.JSONDecodeError as exc:
            logger.error("Configuration JSON mal formée : %s", exc)
            logger.debug("Détail du décodage de la configuration", exc_info=True)
            self._config_vars = _default_config()
            self._unreadable = True
            return
        except (OSError, UnicodeDecodeError) as exc:
            logger.error("Lecture de la configuration impossible : %s", exc)
            logger.debug("Détail de la lecture de la configuration", exc_info=True)
            self._config_vars = _default_config()
            self._unreadable = True
            return

        if not isinstance(loaded_data, dict):
            logger.error("La racine de la configuration doit être un objet JSON")
            self._config_vars = _default_config()
            self._unreadable = True
            return

        self._config_vars = loaded_data.copy()
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Récupère une valeur de configuration.
        
        Args:
            key: Nom de la variable (ex: 'RF_WRK_ENVT')
            default: Valeur par défaut si non trouvée
        
        Returns:
            Valeur de la variable ou default
        """
        json_value = self._config_vars.get(key)
        if json_value is not None:
            return json_value
        
        return default
    
    def set(self, key: str, value: Any) -> bool:
        """
        Définit une valeur de configuration et la sauvegarde dans le JSON.
        
        Args:
            key: Nom de la variable
            value: Valeur à sauvegarder
        
        Returns:
            True si sauvegardé avec succès, False sinon
        """
        previous_value = self._config_vars.get(key, _MISSING)
        self._config_vars[key] = value
        if self._save_config():
            return True

        if previous_value is _MISSING:
            self._config_vars.pop(key, None)
        else:
            self._config_vars[key] = previous_value
        return False
    
    def _save_config(self) -> bool:
        """Sauvegarde atomiquement la configuration dans son fichier JSON.

        La sérialisation est effectuée avant toute écriture. Le contenu est ensuite
        écrit dans un fichier temporaire situé dans le même dossier, puis remplacé
        atomiquement afin de préserver l'ancien JSON en cas d'échec.

        Returns:
            ``True`` si le fichier a été remplacé, sinon ``False``.
        """
        if self._unreadable:
            logger.error("Configuration illisible : %s n'est pas réécrit, il peut contenir des "
                         "secrets. Le corriger, puis recharger la configuration.", self.config_file)
            return False
        temporary_path: Path | None = None
        try:
            serialized_config = json.dumps(self._config_vars, indent=4, ensure_ascii=False)
            self.config_file.parent.mkdir(parents=True, exist_ok=True)

            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.config_file.parent,
                prefix=f".{self.config_file.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_file.write(serialized_config)
                temporary_path = Path(temporary_file.name)

            temporary_path.replace(self.config_file)
            return True
        except (OSError, TypeError) as exc:
            logger.error("Sauvegarde de la configuration impossible : %s", exc)
            logger.debug("Détail de la sauvegarde de la configuration", exc_info=True)
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    logger.debug("Nettoyage du fichier temporaire impossible", exc_info=True)
            return False
    
    def get_all(self) -> dict[str, Any]:
        """Retourne toute la configuration (copie)."""
        return self._config_vars.copy()

    def is_sensitive_key(self, key: str) -> bool:
        """Indique si une variable doit être masquée dans les interfaces publiques."""
        return _is_sensitive_key(key)

    def is_editable_key(self, key: str) -> bool:
        """Indique si une clé connue peut être modifiée depuis l'API locale.

        Les clés déjà présentes restent éditables pour préserver les anciennes
        configurations. Les valeurs par défaut et les réglages UI explicitement
        prévus sont également autorisés. Une nouvelle clé arbitraire est refusée.
        """
        known_keys = self._config_vars.keys() | _default_config().keys() | EXTRA_EDITABLE_KEYS
        return key in known_keys

    def get_public_value(self, key: str) -> Any:
        """Retourne une valeur publiable sans révéler les secrets configurés."""
        value = self._config_vars.get(key)
        if self.is_sensitive_key(key) and value not in (None, ""):
            return MASKED_CONFIG_VALUE
        return value

    def get_public_all(self) -> dict[str, Any]:
        """Retourne la configuration destinée au navigateur avec secrets masqués."""
        return {key: self.get_public_value(key) for key in self._config_vars}
    
    def reload(self) -> None:
        """Recharge la configuration depuis le fichier JSON."""
        self._load_config()
    
    def delete(self, key: str) -> bool:
        """Supprime une variable et restaure la mémoire si l'écriture échoue."""
        if key not in self._config_vars:
            return False

        previous_value = self._config_vars.pop(key)
        if self._save_config():
            return True

        self._config_vars[key] = previous_value
        return False
    
    def __repr__(self) -> str:
        """Retourne une représentation technique sans exposer les valeurs."""
        return f"Config(file={self.config_file}, vars={len(self._config_vars)})"
    
    def __str__(self) -> str:
        """Retourne une vue lisible en masquant les valeurs sensibles."""
        lines = ["Configuration actuelle:"]
        for key, value in sorted(self._config_vars.items()):
            display_value = MASKED_CONFIG_VALUE if _is_sensitive_key(key) else value
            lines.append(f"  {key}: {display_value}")
        return "\n".join(lines)


# ✅ Instance globale (Singleton)
config = Config()
