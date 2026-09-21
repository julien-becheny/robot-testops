*** Settings ***
Documentation       Tests du checkout - processus de commande complet.

Resource  ../../../libraries/resources/web/saucedemo/kw_saucedemo.resource

Test Teardown  Close Browser

Test Tags  saucedemo  checkout  web  regression


*** Test Cases ***
Checkout - Complete Purchase
  [Documentation]  Parcours complet : login, ajout panier, checkout, confirmation.
  [Tags]  e2e  feat:saucedemo.commande.finalisation
  Open Checkout With Product  ${TO_INVENTORY}[BTN_ADD_BACKPACK]
  Fill Checkout Information
  Get Element States  ${TO_CHECKOUT}[LBL_TOTAL]  contains  visible
  Click  ${TO_CHECKOUT}[BTN_FINISH]
  Wait For Screen  saucedemo.checkout.confirmation  ${TO_CHECKOUT}[LBL_COMPLETE]
  Get Text  ${TO_CHECKOUT}[LBL_COMPLETE]  ==  ${TD_SAUCEDEMO}[EXPECTED][ORDER_CONFIRMATION]

Checkout - Missing Information Error
  [Documentation]  Tente un checkout sans remplir les infos et vérifie l'erreur.
  [Tags]  error  feat:saucedemo.commande.controle_saisie
  Open Checkout With Product  ${TO_INVENTORY}[BTN_ADD_BACKPACK]
  Click  ${TO_CHECKOUT}[BTN_CONTINUE]
  Get Element States  ${TO_CHECKOUT}[CTN_ERROR]  contains  visible
  Get Text  ${TO_CHECKOUT}[MSG_ERROR]  contains  ${TD_SAUCEDEMO}[EXPECTED][ERROR_FIRST_NAME]

Checkout - Verify Order Summary
  [Documentation]  Vérifie les détails du résumé avant confirmation.
  [Tags]  summary  feat:saucedemo.commande.resume
  Open Checkout With Product  ${TO_INVENTORY}[BTN_ADD_BACKPACK]
  Fill Checkout Information
  Get Text  ${TO_CHECKOUT}[LBL_ITEM_NAME]  ==  ${TD_SAUCEDEMO}[EXPECTED][PRODUCT_BACKPACK]
  Get Element States  ${TO_CHECKOUT}[LBL_SUBTOTAL]  contains  visible
  Get Element States  ${TO_CHECKOUT}[LBL_TAX]  contains  visible
  Get Element States  ${TO_CHECKOUT}[LBL_TOTAL]  contains  visible
