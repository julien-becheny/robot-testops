*** Settings ***
Documentation       Module SauceDemo - tests web.
...                 Le tag est posé ici, donc hérité par tous les tests du dossier :
...                 impossible de l'oublier en ajoutant un fichier de test.
...                 Ce tag ne sert qu'au filtrage et au reporting. Il ne participe pas à la résolution d'URL.

Test Tags  module:saucedemo
