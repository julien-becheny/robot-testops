*** Settings ***
Documentation       Test de fumée — vérifie que le framework fonctionne.

Resource  ../../../libraries/resources/web/saucedemo/kw_saucedemo.resource

Test Teardown  Close Browser

Test Tags  saucedemo  web  smoke  sanity  feat:saucedemo.connexion.formulaire


*** Test Cases ***
Smoke — Open Browser And Verify Title
  [Documentation]  Ouvre le site SauceDemo et vérifie le titre.
  Open SauceDemo
  Get Title  contains  ${TD_SAUCEDEMO}[EXPECTED][TITLE]

Smoke — Login Page Elements Visible
  [Documentation]  Vérifie que les éléments du formulaire de login sont présents.
  Open SauceDemo
  Get Element States  ${TO_LOGIN}[FLD_USERNAME]  contains  visible
  Get Element States  ${TO_LOGIN}[FLD_PASSWORD]  contains  visible
  Get Element States  ${TO_LOGIN}[BTN_LOGIN]  contains  visible
