*** Settings ***
Documentation       Smoke Appium (Android) : ouvre l'app Réglages et vérifie l'affichage.
...                 Valide la chaîne complète - serveur Appium → appareil → uiautomator2 →
...                 AppiumLibrary → capabilities.py - sans dépendre d'un build applicatif.
...                 L'app cible (Réglages) est définie dans variables_config.json
...                 (RF_ANDROID_PACKAGE / RF_ANDROID_ACTIVITY).
...
...                 C'est le premier test à lancer quand un run mobile échoue : s'il passe, le
...                 problème vient du test ; s'il échoue, il vient de la chaîne Appium.

Resource  ../../libraries/resources/mobile/kw_mobile.resource

Suite Teardown  Close Mobile App


*** Test Cases ***
Smoke - Ouvrir Les Réglages Android
  [Documentation]  Ouvre l'app Réglages et vérifie qu'un élément de l'interface est accessible.
  [Tags]  android
  Open Mobile App
  Wait Until Page Contains Element  //android.widget.TextView  timeout=20s
