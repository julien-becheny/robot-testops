*** Settings ***
Documentation       Keywords métier du parcours d'achat — INDÉPENDANTS DU MOTEUR.
...
...                 Ces keywords disent ce que fait l'utilisateur (« se connecter », « finaliser la
...                 commande ») et n'appellent QUE les primitives de l'adaptateur : Tap, Type,
...                 Type Secret, Wait Visible, Should Show Text. Aucun keyword `Browser` ni
...                 `AppiumLibrary` ne doit apparaître ici — c'est ce qui rend le scénario portable.
...
...                 D'OÙ VIENT CHAQUE CHOSE
...                 - le moteur   → `${ACTIONS}`, injecté au lancement (playwright ou appium) ;
...                 - l'URL       → `config/environments.yaml`, via `Get Module Url` ;
...                 - le compte   → `config/environments.yaml` + le secret de
...                 \                `config/variables_config.json`, via `Get Account` ;
...                 - les locators → `libraries/test_objects/web/saucedemo/to_*.yml`, PARTAGÉS avec
...                 \                les suites web : c'est le même site, donc les mêmes sélecteurs.
...
...                 SauceDemo n'est qu'un support d'entraînement. Ce qui doit survivre, c'est la
...                 forme : scénario neutre, adaptateur par moteur, locators dans test_objects.

Resource  ${ACTIONS}
Library  ${CURDIR}/../common/environment.py
Variables  ${CURDIR}/../../test_objects/web/saucedemo/to_login.yml
Variables  ${CURDIR}/../../test_objects/web/saucedemo/to_inventory.yml
Variables  ${CURDIR}/../../test_objects/web/saucedemo/to_cart.yml
Variables  ${CURDIR}/../../test_objects/web/saucedemo/to_checkout.yml


*** Variables ***
# Écrasé au lancement par `-v ENVIRONMENT:<id>`. Vide, l'environnement actif de la
# configuration est utilisé (cf. core/environments.py).
${ENVIRONMENT}  ${EMPTY}


*** Keywords ***
Ouvrir La Boutique
  [Documentation]  Ouvre le module saucedemo de l'environnement courant, avec le moteur choisi.
  ${Url}=  Get Module Url  saucedemo  ${ENVIRONMENT}
  Open Session  ${Url}
  Wait Visible  ${TO_LOGIN}[BTN_LOGIN]

Se Connecter
  [Documentation]  Se connecte avec un profil déclaré dans l'environnement courant.
  ...  Le mot de passe n'apparaît ni dans le test, ni dans le log.
  [Arguments]  ${Profile}=STANDARD
  ${Account}=  Get Account  ${Profile}  ${ENVIRONMENT}
  Type  ${TO_LOGIN}[FLD_USERNAME]  ${Account}[username]
  Type Secret  ${TO_LOGIN}[FLD_PASSWORD]  ${Account}[password]
  Tap  ${TO_LOGIN}[BTN_LOGIN]
  Wait Visible  ${TO_INVENTORY}[LNK_CART]

Ajouter Deux Articles Au Panier
  [Documentation]  Ajoute le sac à dos et la lampe depuis la liste des produits.
  Tap  ${TO_INVENTORY}[BTN_ADD_BACKPACK]
  Tap  ${TO_INVENTORY}[BTN_ADD_BIKE_LIGHT]

Le Panier Doit Contenir
  [Documentation]  Vérifie le nombre d'articles affiché par la pastille du panier.
  [Arguments]  ${Nombre}
  Should Show Text  ${TO_INVENTORY}[LBL_CART_BADGE]  ${Nombre}

Ouvrir Le Panier Et Passer Au Checkout
  [Documentation]  Ouvre le panier puis démarre le tunnel de commande.
  ...  L'attente porte sur le bouton, pas sur les lignes du panier : `.cart_item` en désigne
  ...  autant qu'il y a d'articles, et Playwright refuse un locator ambigu (mode strict).
  Tap  ${TO_INVENTORY}[LNK_CART]
  Wait Visible  ${TO_CART}[BTN_CHECKOUT]
  Tap  ${TO_CART}[BTN_CHECKOUT]

Remplir Les Informations Client
  [Documentation]  Renseigne l'identité de livraison puis affiche le résumé de commande.
  [Arguments]  ${Prenom}  ${Nom}  ${Code_Postal}
  Type  ${TO_CHECKOUT}[FLD_FIRST_NAME]  ${Prenom}
  Type  ${TO_CHECKOUT}[FLD_LAST_NAME]  ${Nom}
  Type  ${TO_CHECKOUT}[FLD_POSTAL_CODE]  ${Code_Postal}
  Tap  ${TO_CHECKOUT}[BTN_CONTINUE]

Un Total Doit Etre Affiche
  [Documentation]  Vérifie que le résumé de commande présente un total.
  Should Show Text  ${TO_CHECKOUT}[LBL_TOTAL]  Total

Finaliser La Commande
  [Documentation]  Valide définitivement la commande depuis le résumé.
  Tap  ${TO_CHECKOUT}[BTN_FINISH]

La Commande Doit Etre Confirmee
  [Documentation]  Vérifie que l'écran final confirme la commande.
  [Arguments]  ${Message}
  Should Show Text  ${TO_CHECKOUT}[LBL_COMPLETE]  ${Message}
