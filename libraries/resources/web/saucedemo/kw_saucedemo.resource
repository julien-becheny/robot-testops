*** Settings ***
Documentation       Keywords métier du module SauceDemo - TEMPLATE DE RÉFÉRENCE.
...                 Copier ce module pour créer le module d'une nouvelle application :
...                 1. libraries/resources/web/<module>/kw_<module>.resource
...                 2. libraries/test_objects/web/<module>/to_*.yml
...                 3. libraries/test_data/web/<module>/td_<module>.yml
...                 4. test_suites/web/<module>/*.robot
...                 5. test_suites/web/<module>/__init__.robot avec Test Tags  module:<module>
...                 6. déclarer son chemin sous `modules:` dans config/environments.yaml
...                 Règle POM : to_* = locators seuls, kw_* = actions métier, td_* = données.

Resource  ../../common/kw_browser.resource
Variables  ../../../test_data/web/saucedemo/td_saucedemo.yml
Variables  ../../../test_objects/web/saucedemo/to_login.yml
Variables  ../../../test_objects/web/saucedemo/to_inventory.yml
Variables  ../../../test_objects/web/saucedemo/to_cart.yml
Variables  ../../../test_objects/web/saucedemo/to_checkout.yml
Variables  ../../../test_objects/web/saucedemo/to_product_detail.yml


*** Keywords ***
Open SauceDemo
  [Documentation]  Ouvre le navigateur sur la page de login SauceDemo.
  Open Module  saucedemo
  Wait For Screen  saucedemo.connexion  ${TO_LOGIN}[BTN_LOGIN]

Login As
  [Documentation]  Renseigne le formulaire de login et se connecte avec le profil donné.
  ...  Les identifiants dépendent de l'environnement : ils sont résolus à l'exécution.
  [Arguments]  ${Profile}=STANDARD
  ${Account}=  Get Account  ${Profile}  ${ENVIRONMENT}
  Fill Text  ${TO_LOGIN}[FLD_USERNAME]  ${Account}[username]
  Fill Secret  ${TO_LOGIN}[FLD_PASSWORD]  ${Account}[password]
  Click  ${TO_LOGIN}[BTN_LOGIN]

Open And Login As
  [Documentation]  Raccourci : ouvre le navigateur puis se connecte (pré-requis le plus courant).
  [Arguments]  ${Profile}=STANDARD
  Open SauceDemo
  Login As  ${Profile}
  Wait For Screen  saucedemo.inventaire  ${TO_INVENTORY}[LNK_CART]

Add Product To Cart
  [Documentation]  Ajoute un produit au panier via le bouton fourni.
  [Arguments]  ${Add_Button}
  Click  ${Add_Button}

Open Checkout With Product
  [Documentation]  Se connecte, ajoute le produit fourni puis ouvre le formulaire de checkout.
  [Arguments]  ${Add_Button}
  Open And Login As  STANDARD
  Add Product To Cart  ${Add_Button}
  Click  ${TO_INVENTORY}[LNK_CART]
  Wait For Screen  saucedemo.panier  ${TO_CART}[BTN_CHECKOUT]
  Click  ${TO_CART}[BTN_CHECKOUT]
  Wait For Screen  saucedemo.checkout.informations  ${TO_CHECKOUT}[FLD_FIRST_NAME]

Fill Checkout Information
  [Documentation]  Renseigne les informations de livraison par défaut puis affiche le résumé.
  Fill Text  ${TO_CHECKOUT}[FLD_FIRST_NAME]  ${TD_SAUCEDEMO}[CHECKOUT][FIRST_NAME]
  Fill Text  ${TO_CHECKOUT}[FLD_LAST_NAME]  ${TD_SAUCEDEMO}[CHECKOUT][LAST_NAME]
  Fill Text  ${TO_CHECKOUT}[FLD_POSTAL_CODE]  ${TD_SAUCEDEMO}[CHECKOUT][POSTAL_CODE]
  Click  ${TO_CHECKOUT}[BTN_CONTINUE]
  Wait For Screen  saucedemo.checkout.resume  ${TO_CHECKOUT}[LBL_TOTAL]
