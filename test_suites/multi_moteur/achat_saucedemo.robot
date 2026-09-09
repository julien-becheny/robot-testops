*** Settings ***
Documentation       Parcours d'achat SauceDemo — ÉCRIT UNE FOIS, JOUÉ SUR DEUX MOTEURS.
...
...                 Le corps du test ne connaît ni Playwright ni Appium : il n'appelle que des
...                 keywords métier, qui eux-mêmes n'appellent que les primitives de l'adaptateur
...                 désigné par `${ACTIONS}` au lancement.
...
...                 COMMENT LE JOUER
...                 - Playwright : c'est le cas par défaut. Rien à faire, il part avec les autres.
...                 - Appium     : bouton « Tests sur mobile physique » de TestOps, ou à la main
...                 \  (`${ACTIONS}` doit être ABSOLU : Robot résout un chemin relatif depuis le
...                 \  fichier qui l'importe, pas depuis le répertoire courant)
...                 \  robot -v ACTIONS:$PWD/libraries/resources/common/actions_appium.resource
...                 \        -v ENVIRONMENT:saucedemo test_suites/multi_moteur/
...
...                 Voir test_suites/multi_moteur/README.md pour la raison d'être de ce dossier.

Resource  ../../libraries/resources/multi_moteur/kw_achat.resource
Variables  ../../libraries/test_data/web/saucedemo/td_saucedemo.yml

Suite Teardown  Close Session

Test Tags  saucedemo  achat


*** Test Cases ***
Achat — Deux Articles Jusqu'à La Confirmation
  [Documentation]  Connexion, ajout de deux articles, tunnel de commande, confirmation.
  [Tags]  feat:saucedemo.panier.ajout_article  feat:saucedemo.commande.finalisation
  Ouvrir La Boutique
  Se Connecter  STANDARD
  Ajouter Deux Articles Au Panier
  Le Panier Doit Contenir  2
  Ouvrir Le Panier Et Passer Au Checkout
  Remplir Les Informations Client
  ...  ${TD_SAUCEDEMO}[CHECKOUT][FIRST_NAME]
  ...  ${TD_SAUCEDEMO}[CHECKOUT][LAST_NAME]
  ...  ${TD_SAUCEDEMO}[CHECKOUT][POSTAL_CODE]
  Un Total Doit Etre Affiche
  Finaliser La Commande
  La Commande Doit Etre Confirmee  ${TD_SAUCEDEMO}[EXPECTED][ORDER_CONFIRMATION]
