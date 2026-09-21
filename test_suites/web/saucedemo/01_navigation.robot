*** Settings ***
Documentation       Tests de navigation - vérifie la navigation entre pages SauceDemo.

Resource  ../../../libraries/resources/web/saucedemo/kw_saucedemo.resource

Test Teardown  Close Browser

Test Tags  saucedemo  navigation  web  regression


*** Test Cases ***
Navigation - Login And Access Inventory
  [Documentation]  Se connecte et vérifie l'accès à la page inventaire.
  [Tags]  login  feat:saucedemo.connexion.identifiants_valides
  Open And Login As  STANDARD
  Get Url  contains  inventory
  Get Title  contains  ${TD_SAUCEDEMO}[EXPECTED][TITLE]

Navigation - Access Product Detail
  [Documentation]  Se connecte, clique sur un produit et vérifie la page détail.
  [Tags]  product  feat:saucedemo.catalogue.consultation_produit
  Open And Login As  STANDARD
  Click  ${TO_INVENTORY}[LNK_PRODUCT_FIRST]
  Wait For Screen  saucedemo.produit.detail  ${TO_PRODUCT_DETAIL}[CTN_DETAILS]
  Get Url  contains  inventory-item
  Get Element States  ${TO_PRODUCT_DETAIL}[CTN_DETAILS]  contains  visible
  Click  ${TO_PRODUCT_DETAIL}[BTN_BACK]
  Get Url  contains  inventory

Navigation - Sidebar Menu
  [Documentation]  Ouvre le menu latéral et vérifie les liens disponibles.
  [Tags]  menu  feat:saucedemo.navigation.menu_lateral
  Open And Login As  STANDARD
  Click  ${TO_INVENTORY}[BTN_BURGER_MENU]
  Wait For Screen  saucedemo.menu_lateral  ${TO_INVENTORY}[LNK_SIDEBAR_LOGOUT]
  Get Element States  ${TO_INVENTORY}[LNK_SIDEBAR_INVENTORY]  contains  visible
  Get Element States  ${TO_INVENTORY}[LNK_SIDEBAR_ABOUT]  contains  visible
  Get Element States  ${TO_INVENTORY}[LNK_SIDEBAR_LOGOUT]  contains  visible
  Click  ${TO_INVENTORY}[BTN_CLOSE_MENU]
