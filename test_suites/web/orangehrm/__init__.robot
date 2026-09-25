*** Settings ***
Documentation       Module OrangeHRM - tests web.
...                 Le tag est posé ici, donc hérité par tous les tests du dossier :
...                 impossible de l'oublier en ajoutant un fichier de test.
...                 Ce tag ne sert qu'au filtrage et au reporting. Il ne participe pas à la résolution d'URL.
...
...                 CONNEXION UNE SEULE FOIS
...                 Le `Suite Setup` joue le formulaire de connexion et garde la session ; les
...                 tests du dossier ouvrent ensuite un contexte déjà authentifié. Deux effets :
...                 - si la connexion casse, AUCUN test ne s'exécute, et le rapport montre un
...                 \  seul échec à l'endroit de la panne au lieu de N échecs identiques ;
...                 - la session vit dans un fichier temporaire propre au processus, hors du
...                 \  dossier de rapport, effacé par le `Suite Teardown` (cf. common/auth_state.py).

Resource  ../../../libraries/resources/web/orangehrm/kw_orangehrm.resource

Suite Setup  Log In Once For The Suite  ADMIN
Suite Teardown  Forget Login State

Test Tags  module:orangehrm
