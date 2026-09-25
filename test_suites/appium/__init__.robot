*** Settings ***
Documentation       Suites APPIUM - n'ont de sens que sur un appareil réel ou un émulateur.
...                 Le tag est posé ici, donc hérité par tous les tests du dossier.
...
...                 Ce tag EST exclu des runs habituels (`-e appium` dans
...                 services/execution/commands.py) : sans appareil connecté ni serveur Appium,
...                 ces tests échoueraient sans rien apprendre à personne. Ils se lancent depuis
...                 le bouton « Tests sur mobile physique » de TestOps, qui démarre Appium d'abord.
...
...                 À ne pas confondre avec test_suites/multi_moteur/, dont les tests tournent
...                 sur les DEUX moteurs. Ici, on écrit du spécifiquement mobile.

Test Tags  appium
