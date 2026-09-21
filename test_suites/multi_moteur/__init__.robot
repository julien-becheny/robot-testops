*** Settings ***
Documentation       Suites MULTI-MOTEUR - un même scénario, jouable avec Playwright ou Appium.
...                 Le tag est posé ici, donc hérité par tous les tests du dossier.
...
...                 Ce tag ne sert PAS à exclure : ces tests partent dans les runs habituels
...                 (smoke, tags, campagnes), joués avec Playwright. Il sert à les reconnaître,
...                 et à les rejouer sur un appareil réel depuis TestOps.

Test Tags  multi_moteur
