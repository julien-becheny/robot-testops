*** Settings ***
Documentation       Tests du panier — ajout, suppression et vérification des articles.

Resource  ../../../libraries/resources/web/saucedemo/kw_saucedemo.resource

Test Teardown  Close Browser

Test Tags  saucedemo  cart  web  regression


*** Test Cases ***
Cart — Add Single Item
  [Documentation]  Ajoute un article au panier et vérifie le badge.
  [Tags]  add  feat:saucedemo.panier.ajout_article
  Open And Login As  STANDARD
  Add Product To Cart  ${TO_INVENTORY}[BTN_ADD_BACKPACK]
  Get Text  ${TO_INVENTORY}[LBL_CART_BADGE]  ==  1

Cart — Add Multiple Items
  [Documentation]  Ajoute plusieurs articles et vérifie le compteur.
  [Tags]  add  feat:saucedemo.panier.ajout_article
  Open And Login As  STANDARD
  Add Product To Cart  ${TO_INVENTORY}[BTN_ADD_BACKPACK]
  Add Product To Cart  ${TO_INVENTORY}[BTN_ADD_BIKE_LIGHT]
  Add Product To Cart  ${TO_INVENTORY}[BTN_ADD_BOLT_TSHIRT]
  Get Text  ${TO_INVENTORY}[LBL_CART_BADGE]  ==  3

Cart — Remove Item
  [Documentation]  Ajoute un article puis le retire du panier.
  [Tags]  remove  feat:saucedemo.panier.retrait_article
  Open And Login As  STANDARD
  Add Product To Cart  ${TO_INVENTORY}[BTN_ADD_BACKPACK]
  Get Text  ${TO_INVENTORY}[LBL_CART_BADGE]  ==  1
  Click  ${TO_INVENTORY}[BTN_REMOVE_BACKPACK]
  Get Element States  ${TO_INVENTORY}[LBL_CART_BADGE]  not contains  visible

Cart — View Cart Page
  [Documentation]  Ajoute un article et vérifie la page panier.
  [Tags]  view  feat:saucedemo.panier.consultation
  Open And Login As  STANDARD
  Add Product To Cart  ${TO_INVENTORY}[BTN_ADD_BACKPACK]
  Click  ${TO_INVENTORY}[LNK_CART]
  Wait For Screen  saucedemo.panier  ${TO_CART}[CTN_CART_ITEM]
  Get Url  contains  cart
  Get Element States  ${TO_CART}[CTN_CART_ITEM]  contains  visible
  Get Text  ${TO_CART}[LBL_ITEM_NAME]  ==  ${TD_SAUCEDEMO}[EXPECTED][PRODUCT_BACKPACK]
