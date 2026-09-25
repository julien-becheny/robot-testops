*** Settings ***
Documentation       Keywords partagés pour la gestion du navigateur (couche commune, tous modules web).

Library  Collections
Library  Browser
Library  ${CURDIR}/auth_state.py
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
# Session enregistrée par `Remember Login State`. Vide = chaque test se connecte lui-même.
${AUTH_STATE}  ${EMPTY}


*** Keywords ***
Open Test Browser
  [Documentation]  Ouvre un navigateur avec le profil d'appareil complet
  ...  (viewport, user-agent, densité, tactile) et, optionnellement, une URL.
  ...  ${SLOW_MO} (durée RF, ex. 0:00:01) ralentit chaque action Playwright ; 0:00:00 = off.
  ...  ${TRACING} enregistre la trace du test sous <rapport>/browser/traces/.
  ...  ${AUTH_STATE}, s'il est posé, ouvre le contexte déjà connecté.
  [Arguments]  ${Url}=${EMPTY}
  ${Ctx_Kwargs}=  Get New Context Kwargs  ${BROWSER}  ${DEVICE}
  ${Trace}=  Get Trace Target
  IF  $Trace  Set To Dictionary  ${Ctx_Kwargs}  tracing=${Trace}
  IF  $AUTH_STATE  Set To Dictionary  ${Ctx_Kwargs}  storageState=${AUTH_STATE}
  New Browser  ${BROWSER}  headless=${HEADLESS}  slowMo=${SLOW_MO}
  New Context  &{Ctx_Kwargs}
  IF  '${Url}' != '${EMPTY}'  New Page  ${Url}

Remember Login State
  [Documentation]  Enregistre la session du contexte courant pour les tests suivants.
  ...  À appeler depuis un `Suite Setup`, APRÈS avoir vérifié que la connexion a abouti :
  ...  sans cette vérification, un login raté enregistrerait un état vide et les tests
  ...  échoueraient plus loin, sur des symptômes qui ne parlent plus de connexion.
  ...  Le fichier produit par `Save Storage State` contient le cookie de session : il est
  ...  sorti du dossier de rapport sans délai (cf. common/auth_state.py).
  ${Saved}=  Save Storage State
  ${State}=  Stash Auth State  ${Saved}
  Set Global Variable  ${AUTH_STATE}  ${State}

Forget Login State
  [Documentation]  Efface la session enregistrée. À appeler en `Suite Teardown` :
  ...  un état vivant ne doit pas survivre au run qui l'a créé.
  Discard Auth State
  Set Global Variable  ${AUTH_STATE}  ${EMPTY}

Open Module
  [Documentation]  Ouvre le navigateur sur un module, dans l'environnement courant.
  ...  Le test nomme son module ; l'URL est composée à l'exécution à partir de
  ...  config/environments.yaml. Aucune URL n'est écrite dans un test.
  [Arguments]  ${Module}
  ${Url}=  Get Module Url  ${Module}  ${ENVIRONMENT}
  Open Test Browser  ${Url}

Wait For Screen
  [Documentation]  Attend l'élément caractéristique d'un écran, et trace son identifiant.
  ...  \${Screen_Id} doit exister dans functional_map/ : c'est ce qui alimente la couverture
  ...  fonctionnelle (`python tools/coverage.py`), qui refuse tout identifiant inconnu.
  [Arguments]  ${Screen_Id}  ${Locator}
  Log  Écran : ${Screen_Id}
  Wait For Elements State  ${Locator}  visible  timeout=15s
