"""
Module de gestion des tags de tests.

Expose :
- parser: Parsing des fichiers .robot pour extraire les tags
- manager: Filtrage et matching des tests par tags
"""

from .manager import count_tests_matching_tags, get_available_tags, get_matching_tests
from .parser import build_tests_list, get_robot_files

__all__ = [
    'get_robot_files',
    'build_tests_list',
    'get_available_tags',
    'get_matching_tests',
    'count_tests_matching_tags',
]
