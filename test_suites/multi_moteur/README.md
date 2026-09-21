# Tests multi-moteur

Les tests de ce dossier sont écrits **une seule fois** et se jouent **sur deux moteurs** :
Playwright (navigateur du poste) et Appium (appareil Android connecté). Le test ne sait pas
lequel le pilote.

## Pourquoi ce dossier existe

Un test Robot Framework est écrit dans le vocabulaire d'une librairie. `Click` appartient à
`Browser` (Playwright), `Click Element` à `AppiumLibrary` : le même fichier ne peut pas
s'exécuter des deux côtés sans traduction. C'est cette traduction qui vit dans
`libraries/resources/common/actions_playwright.resource` et `actions_appium.resource`.

L'intérêt n'est pas théorique : il permet de vérifier sur un **téléphone réel** un parcours
déjà couvert en émulation, sans le réécrire - clavier virtuel, gestes, performances réelles,
Safari iOS le jour venu. Ce que l'émulation ne peut pas reproduire.

## Les trois couches

| Couche | Où | Rôle |
|---|---|---|
| Scénario | `test_suites/multi_moteur/*.robot` | ce que fait l'utilisateur, en métier |
| Keywords métier | `libraries/resources/multi_moteur/kw_*.resource` | traduit le métier en primitives |
| Adaptateur | `libraries/resources/common/actions_*.resource` | traduit les primitives par moteur |

Les locators, eux, ne sont **pas** dupliqués : ce sont ceux des suites web
(`libraries/test_objects/web/saucedemo/to_*.yml`). Même site, mêmes sélecteurs.

## Comment les lancer

**Playwright** - rien à faire. Ces tests partent avec les runs habituels (smoke, tags,
campagnes), qui injectent l'adaptateur Playwright par défaut.

**Appium** - bouton « Tests sur mobile physique » dans TestOps. Il démarre le serveur Appium,
attend qu'il réponde, puis joue ce dossier et `test_suites/appium/` avec l'adaptateur Appium.

À la main - `${ACTIONS}` doit être un chemin **absolu** : Robot résout un chemin relatif
depuis le fichier qui l'importe, pas depuis le répertoire courant.

```powershell
.\env\Scripts\robot.exe `
  -v ACTIONS:$PWD/libraries/resources/common/actions_appium.resource `
  -v ENVIRONMENT:saucedemo `
  -d temp\run_mobile test_suites\multi_moteur
```

## Ce qu'on peut écrire ici - et ce qu'on ne peut pas

Un test de ce dossier n'appelle **que** les primitives de l'adaptateur : `Open Session`,
`Close Session`, `Tap`, `Type`, `Type Secret`, `Wait Visible`, `Should Show Text`.

Pour ajouter une capacité, il faut l'écrire dans **les deux** adaptateurs, avec le même nom et
le même contrat, chacun au mieux de son moteur. Une capacité qui n'a pas d'équivalent partout
(l'URL de la page, par exemple, qui n'existe pas dans une application native) n'a rien à faire
ici : elle appartient à une suite mono-moteur, sous `test_suites/web/`, qui appelle `Browser`
directement et garde toute sa richesse.

C'est le prix de la portabilité, et c'est pourquoi **tout ne doit pas venir ici**. Seuls les
parcours qui gagnent vraiment à être rejoués sur un appareil réel le méritent.

## Le contexte, pour s'y retrouver plus tard

La pratique courante du métier, pour un site web responsive, est de tester en **émulation**
(viewport + user-agent + tactile) et de ne sortir l'appareil réel que sur quelques parcours.
L'émulation est déjà en place ici : c'est le sélecteur « Appareils » de TestOps, via
`libraries/resources/common/device_profiles.py`.

Une **application native**, elle, imposera Appium et une suite séparée : les écrans et les
locators n'ont plus rien de commun avec le web. Ce dossier ne sert donc pas à ça - il sert au
cas intermédiaire : le même site, vu depuis un vrai téléphone.

SauceDemo n'est qu'un support d'entraînement. Ce qui doit survivre, c'est la forme.
