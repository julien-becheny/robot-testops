*** Settings ***
Documentation       Keywords partagés pour la gestion du navigateur (couche commune, tous modules web).

Library  Collections
Library  Browser
Library  ${CURDIR}/device_profiles.py
Library  ${CURDIR}/environment.py
Library  ${CURDIR}/tracing.py


*** Variables ***
${BROWSER}  chromium
${DEVICE}  desktop
${ENVIRONMENT}  ${EMPTY}
${HEADLESS}  ${FALSE}
${SLOW_MO}  0:00:00
${TRACING}  ${TRUE}


*** Keywords ***
Open Test Browser
  [Documentation]  Ouvre un navigateur avec le profil d'appareil complet
  ...  (viewport, user-agent, densité, tactile) et, optionnellement, une URL.
  ...  ${SLOW_MO} (durée RF, ex. 0:00:01) ralentit chaque action Playwright ; 0:00:00 = off.
  ...  ${TRACING} enregistre la trace du test sous <rapport>/browser/traces/.
  [Arguments]  ${Url}=${EMPTY}
  ${Ctx_Kwargs}=  Get New Context Kwargs  ${BROWSER}  ${DEVICE}
  ${Trace}=  Get Trace Target
  IF  $Trace  Set To Dictionary  ${Ctx_Kwargs}  tracing=${Trace}
  New Browser  ${BROWSER}  headless=${HEADLESS}  slowMo=${SLOW_MO}
  New Context  &{Ctx_Kwargs}
  IF  '${Url}' != '${EMPTY}'  New Page  ${Url}

Open Module
  [Documentation]  Ouvre le navigateur sur un module, dans l'environnement courant.
  ...  Le test nomme son module ; l'URL est composée à l'exécution à partir de
  ...  config/environments.yaml. Aucune URL n'est écrite dans un test.
  [Arguments]  ${Module}
  ${Url}=  Get Module Url  ${Module}  ${ENVIRONMENT}
  Open Test Browser  ${Url}

Wait For Screen
  [Documentation]  Attend l'élément caractéristique d'un écran, et trace son identifiant.
  ...  L'identifiant nomme l'écran traversé : le rapport se lit alors comme un parcours,
  ...  et non comme une suite de locators.
  [Arguments]  ${Screen_Id}  ${Locator}
  Log  Écran : ${Screen_Id}
  Wait For Elements State  ${Locator}  visible  timeout=15s
