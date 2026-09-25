*** Settings ***
Documentation       Socle mobile Appium (Android + iOS) - SKELETON, non branché pour l'instant.
...                 Prêt à l'emploi dès que l'application mobile cible et un serveur Appium seront disponibles.
...
...                 Principes :
...                 - AppiumLibrary est poussé via l'orchestrateur (services/execution), jamais lancé en direct.
...                 - Ne JAMAIS mélanger Browser (Playwright) et AppiumLibrary dans une même suite.
...                 - Les capabilities (Android/iOS) sont centralisées dans libraries/mobile/capabilities.py,
...                 lues depuis variables_config.json - rien de hardcodé ici.
...                 - Les différences Android/iOS de locators vivent dans les to_*.py (helper loc()),
...                 jamais dans la logique de test.
...                 - Le pont web <-> mobile se fait par la donnée (backend), pas par un driver partagé.

Variables  ../../mobile/capabilities.py
Library  AppiumLibrary


*** Keywords ***
Open Mobile App
  [Documentation]  Ouvre l'application mobile avec les capabilities de la plateforme
  ...  courante (pilotée par RF_MOBILE_PLATFORM).
  Open Application  ${APPIUM_URL}  &{MOBILE_CAPABILITIES}

Close Mobile App
  [Documentation]  Ferme l'application et la session Appium.
  Close Application
