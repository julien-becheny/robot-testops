"""Pièces Python de l'adaptateur Appium - ce que Robot Framework seul ne sait pas faire.

Deux besoins, deux fonctions :

1. :func:`as_appium_locator` - les fichiers ``libraries/test_objects/**/to_*.yml`` écrivent
   des sélecteurs CSS nus (``input#user-name``), parce que c'est ce que ``Browser`` attend.
   AppiumLibrary, lui, coupe le locator au premier ``=`` pour en déduire une stratégie :
   ``h3[data-test='error']`` lui ferait chercher une stratégie nommée ``h3[data-test``.
   On préfixe donc ``css=`` quand aucune stratégie connue n'est présente.

2. :func:`input_secret` - ``Input Password`` masque bien la valeur dans le log, mais attend
   une chaîne. Lui passer directement l'objet ``Secret`` de Robot ferait saisir le texte
   ``<secret>`` dans le champ. Ce keyword ouvre l'enveloppe côté Python, où la valeur ne
   transite par aucun log Robot.

Importé côté Robot via ::

    Library  ${CURDIR}/appium_actions.py
"""

# Third-party
from robot.api.types import Secret
from robot.libraries.BuiltIn import BuiltIn

# Stratégies reconnues par AppiumLibrary (AppiumLibrary/locators/elementfinder.py).
# Figées ici plutôt que lues dans l'attribut privé de la librairie : une stratégie oubliée
# donne une erreur lisible au premier run, un attribut privé disparu casserait l'import.
_STRATEGIES = frozenset({
    "identifier", "id", "name", "xpath", "class", "accessibility_id", "android",
    "viewtag", "data_matcher", "view_matcher", "ios", "css", "jquery", "predicate", "chain",
})


def as_appium_locator(locator: str) -> str:
    """Retourne un locator exploitable par AppiumLibrary.

    Un XPath (``//…``) et une stratégie explicite (``id=``, ``xpath=``, ``css=``…) passent
    tels quels ; tout le reste est considéré comme du CSS et préfixé.
    """
    if locator.startswith("//"):
        return locator
    prefix, separator, _ = locator.partition("=")
    if separator and prefix.strip().lower() in _STRATEGIES:
        return locator
    return f"css={locator}"


def input_secret(locator: str, secret: Secret) -> None:
    """Saisit un mot de passe dans un champ, sans jamais l'exposer au log Robot."""
    appium = BuiltIn().get_library_instance("AppiumLibrary")
    appium.input_password(as_appium_locator(locator), secret.value)
