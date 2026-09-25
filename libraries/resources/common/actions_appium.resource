*** Settings ***
Documentation       Adaptateur APPIUM - traduit les primitives multi-moteur en keywords `AppiumLibrary`.
...
...                 À QUOI SERT CE FICHIER
...                 Jumeau de `actions_playwright.resource` : les suites de
...                 `test_suites/multi_moteur/` sont écrites une seule fois, et c'est la variable
...                 `${ACTIONS}` - injectée au lancement par `services/execution/commands.py` - qui
...                 décide du moteur. Ce fichier est choisi par le bouton « Tests sur mobile
...                 physique » de TestOps. Le serveur Appium est démarré en amont par
...                 `services/mobile/appium_server.py`.
...
...                 CE QUE CET ADAPTATEUR ABSORBE (et que les tests n'ont donc pas à savoir)
...                 - La session : Appium ouvre Chrome SUR l'appareil (WEB_ANDROID_CAPABILITIES),
...                 \  là où Playwright lance un navigateur sur le poste.
...                 - L'attente : Appium n'attend rien tout seul. Chaque action est précédée d'une
...                 \  attente de visibilité explicite ; Playwright, lui, le fait nativement.
...                 - Le format des locators : les `to_*.yml` écrivent du CSS nu, qu'AppiumLibrary
...                 \  ne sait pas reconnaître (cf. `appium_actions.as_appium_locator`).
...                 - Le mot de passe : `Input Password` masque le log mais n'accepte pas l'objet
...                 \  `Secret` de Robot (cf. `appium_actions.input_secret`).
...
...                 Toute primitive ajoutée ici doit l'être aussi dans `actions_playwright.resource`,
...                 avec le même nom et le même contrat - sinon les suites cessent d'être portables.

Library  AppiumLibrary
Library  ${CURDIR}/appium_actions.py
Variables  ${CURDIR}/../../mobile/capabilities.py


*** Variables ***
# Marge large : un appareil réel est plus lent qu'un navigateur local, et ce délai remplace
# l'attente automatique dont bénéficie Playwright.
${APPIUM_TIMEOUT}  20


*** Keywords ***
Open Session
  [Documentation]  Ouvre Chrome sur l'appareil connecté puis navigue vers l'URL demandée.
  ...  Aucun UDID n'est imposé : Appium prend l'appareil disponible, physique ou émulateur.
  [Arguments]  ${Url}
  Open Application  ${APPIUM_URL}  &{WEB_ANDROID_CAPABILITIES}
  Go To Url  ${Url}

Close Session
  [Documentation]  Termine la session Appium et referme l'application pilotée.
  Close Application

Tap
  [Documentation]  Attend qu'un élément soit visible puis le touche.
  [Arguments]  ${Locator}
  ${Cible}=  As Appium Locator  ${Locator}
  Wait Until Element Is Visible  ${Cible}  timeout=${APPIUM_TIMEOUT}
  Click Element  ${Cible}

Type
  [Documentation]  Attend un champ puis y saisit le texte demandé.
  [Arguments]  ${Locator}  ${Text}
  ${Cible}=  As Appium Locator  ${Locator}
  Wait Until Element Is Visible  ${Cible}  timeout=${APPIUM_TIMEOUT}
  Input Text  ${Cible}  ${Text}

Type Secret
  [Documentation]  Saisit un mot de passe sans jamais l'écrire dans le log Robot.
  ...  \${Secret} vient de `Get Account` (cf. common/environment.py) - jamais d'une chaîne en clair.
  [Arguments]  ${Locator}  ${Secret}
  ${Cible}=  As Appium Locator  ${Locator}
  Wait Until Element Is Visible  ${Cible}  timeout=${APPIUM_TIMEOUT}
  Input Secret  ${Cible}  ${Secret}

Wait Visible
  [Documentation]  Attend qu'un élément devienne visible.
  [Arguments]  ${Locator}
  ${Cible}=  As Appium Locator  ${Locator}
  Wait Until Element Is Visible  ${Cible}  timeout=${APPIUM_TIMEOUT}

Should Show Text
  [Documentation]  Vérifie que le texte d'un élément contient la valeur attendue.
  ...  L'assertion est rejouée jusqu'à convergence : contrairement à Playwright, AppiumLibrary
  ...  ne réessaie rien, et une lecture unique manquerait un affichage asynchrone.
  [Arguments]  ${Locator}  ${Expected}
  ${Cible}=  As Appium Locator  ${Locator}
  Wait Until Element Is Visible  ${Cible}  timeout=${APPIUM_TIMEOUT}
  Wait Until Keyword Succeeds  20x  0.5s
  ...  Element Should Contain Text  ${Cible}  ${Expected}
