*** Settings ***
Documentation       Adaptateur PLAYWRIGHT — traduit les primitives multi-moteur en keywords `Browser`.
...
...                 À QUOI SERT CE FICHIER
...                 Les suites de `test_suites/multi_moteur/` sont écrites UNE SEULE FOIS, dans un
...                 vocabulaire neutre (Tap, Type, Wait Visible…). Au lancement, la variable
...                 `${ACTIONS}` désigne l'adaptateur à utiliser :
...                 \  - runs habituels (smoke, tags, campagnes) → ce fichier ;
...                 \  - bouton « Tests sur mobile physique »    → actions_appium.resource.
...                 C'est `services/execution/commands.py` qui injecte `-v ACTIONS:<chemin>`.
...
...                 RÈGLES AVANT D'AJOUTER UNE PRIMITIVE
...                 1. Toute primitive doit exister dans LES DEUX adaptateurs, même nom, même
...                 \  signature, même contrat. Sinon un test « multi-moteur » ne l'est plus.
...                 2. Une capacité qui n'a pas de sens partout (URL ou titre de page dans une
...                 \  application native, par exemple) n'a rien à faire ici : elle appartient à
...                 \  une suite mono-moteur, qui appelle sa librairie directement.
...                 3. Chaque adaptateur implémente AU MIEUX de son moteur, jamais au plus petit
...                 \  dénominateur commun. Ici, on utilise les assertions natives de `Browser`,
...                 \  réessayées pendant `retry_assertions_for` (1 s par défaut) : c'est plus
...                 \  robuste qu'une lecture suivie d'une comparaison.
...
...                 Les suites de `test_suites/web/` n'utilisent PAS cet adaptateur : elles
...                 appellent `Browser` directement et gardent accès à toute sa richesse.

Resource  ${CURDIR}/kw_browser.resource


*** Keywords ***
Open Session
  [Documentation]  Ouvre le navigateur sur l'URL demandée, avec le profil d'appareil du run
  ...  (viewport, user-agent, tactile) et le ralenti configuré.
  [Arguments]  ${Url}
  Open Test Browser  ${Url}

Close Session
  [Documentation]  Ferme tous les navigateurs ouverts par l'adaptateur.
  Close Browser  ALL

Tap
  [Documentation]  Clique sur un élément. Playwright attend seul qu'il soit visible et actionnable.
  [Arguments]  ${Locator}
  Click  ${Locator}

Type
  [Documentation]  Remplace le contenu d'un champ par le texte demandé.
  [Arguments]  ${Locator}  ${Text}
  Fill Text  ${Locator}  ${Text}

Type Secret
  [Documentation]  Saisit un mot de passe sans jamais l'écrire dans le log Robot.
  ...  \${Secret} vient de `Get Account` (cf. common/environment.py) — jamais d'une chaîne en clair.
  [Arguments]  ${Locator}  ${Secret}
  Fill Secret  ${Locator}  ${Secret}

Wait Visible
  [Documentation]  Attend qu'un élément devienne visible.
  [Arguments]  ${Locator}
  Wait For Elements State  ${Locator}  visible  timeout=15s

Should Show Text
  [Documentation]  Vérifie que le texte d'un élément contient la valeur attendue.
  ...  L'assertion est portée par `Get Text` lui-même : Playwright la rejoue tant qu'elle échoue,
  ...  ce qui absorbe un affichage asynchrone. Ne pas la remplacer par une lecture puis un
  ...  `Should Contain`, qui ne compare qu'une fois.
  [Arguments]  ${Locator}  ${Expected}
  Get Text  ${Locator}  contains  ${Expected}
