"""
Module central de configuration du projet TestOps.
Fournit un accès unifié à la configuration et aux chemins.
"""

from . import api_config
from .config import Config, config
from .paths import Paths, paths

__all__ = [
    'config', 'Config',
    'paths', 'Paths',
    'api_config',
]

__version__ = '1.0.0'
