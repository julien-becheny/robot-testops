# robot-testops

Une interface web pour piloter des tests **Robot Framework** : choisir la cible, lancer une
suite, suivre les logs en direct, ouvrir le rapport. Backend Flask + Socket.IO, frontend
React, exécution Playwright via [Browser library](https://marketsquare.github.io/robotframework-browser/).

Les suites livrées visent deux applications de démonstration publiques — **SauceDemo** et
**OrangeHRM** — pour que le dépôt soit exécutable tel quel, sans configuration ni compte.

**→ [Voir l'interface en ligne](https://julien-becheny.github.io/robot-testops/)** — un run
réel y est rejoué (logs, étapes, verdict, rapport Robot Framework). Rien n'y est exécuté :
le backend est simulé, les données viennent d'une exécution enregistrée.

[![L'accueil de TestOps : choix entre un smoke test et une exécution par tags, avec le contexte du run affiché en entête](docs/img/testops-accueil.png)](https://julien-becheny.github.io/robot-testops/)

> Le code et la documentation sont en français, langue de travail du projet.

## Le problème qu'il résout

Robot Framework s'exécute très bien en ligne de commande. Ce qui manque, en équipe, c'est
tout ce qu'il y a autour : savoir **sur quel environnement** part un run, **ce qu'il va
jouer**, ce qui se passe **pendant**, et où est le rapport **après**. Ces informations
finissent en général dans un script maison par projet, ou dans la tête d'une personne.

TestOps les rassemble dans une interface, avec trois partis pris :

- **Aucune URL dans les tests.** Un test déclare le *module* qu'il traverse ; l'URL est
  composée à l'exécution à partir de [config/environments.yaml](config/environments.yaml).
  Changer d'environnement ne touche pas une ligne de test.
- **Aucun mot de passe versionné.** Les comptes désignent une *référence* ; la valeur vit
  dans `config/variables_config.json`, ignoré par Git.
- **Un run part d'un contexte explicite.** Navigateur, appareil émulé, environnement et
  ralenti sont visibles en haut de l'écran, figés au lancement — et un run visant une
  cible marquée `prod` demande confirmation.

## Démarrage

Prérequis : Python 3.12+, Node.js 22.12+.

```bash
# Installation (venv, dépendances Python et Node, navigateurs Playwright)
setup.bat            # Windows
./setup.sh           # macOS / Linux

# Renseigner les mots de passe des comptes de démonstration
cp config/variables_config.json.example config/variables_config.json
```

Le fichier d'exemple liste les clés attendues. Pour les cibles publiques livrées, ce sont
les identifiants que ces sites affichent eux-mêmes sur leur page de connexion.

```bash
start_testops_windows.bat     # Windows : backend + frontend
./start_testops_mac.sh        # macOS / Linux
```

L'interface s'ouvre sur `http://localhost:3000`, l'API écoute sur `127.0.0.1:5001`.

Sans interface, en ligne de commande :

```bash
robot test_suites/web/saucedemo/00_smoke.robot
```

## Ce que fait l'interface

| Écran | Ce qu'on y fait |
| --- | --- |
| Accueil | L'état de la chaîne : combien de tests, quelle cible, quel navigateur |
| Smoke test | Ce que le run va jouer, sur quelles combinaisons, puis on lance |
| Exécution par tags | On compose une sélection ; le nombre de tests concernés s'affiche avant de lancer |
| Exécution | Logs en direct, chronomètre, arrêt manuel, lien vers le rapport |
| Configuration | Environnement cible, ralenti, trace Playwright |

Un run lancé continue de vivre quand on navigue ailleurs : la page d'exécution reste
montée tant qu'une session existe, et le rail affiche un badge tant qu'un run tourne.

![Suivi d'exécution : deux tests passés en trois secondes, chaque étape dépliée sous son test](docs/img/testops-execution.png)

## Organisation

```
api/            Routes HTTP fines — aucune logique métier
services/       La logique : composition des commandes, orchestration, exécution
core/           Chemins, configuration, environnements, registre des sessions
robot_listeners/ Listener Robot Framework qui pousse l'avancement vers l'API
libraries/      Keywords, objets de test et données, par application
test_suites/    Les tests
testops/        Frontend React (Vite)
unit_tests/     Tests du backend et des services
```

Trois règles tiennent l'ensemble :

1. Les chemins passent par `core.paths.paths`, jamais en dur.
2. La configuration passe par `core.config`, jamais par `os.environ` directement.
3. Robot Framework s'exécute par `services.execution.runner.execute_rf_commands`, jamais
   par un `subprocess` isolé — c'est ce qui garantit qu'un arrêt manuel est respecté.

## Écrire un test

Un test nomme son module et ses écrans ; il ne connaît ni URL, ni mot de passe.

```robotframework
*** Settings ***
Resource       ../../../libraries/resources/web/saucedemo/kw_saucedemo.resource
Test Teardown  Close Browser
Test Tags      saucedemo  cart  web  regression

*** Test Cases ***
Cart — Add Single Item
  [Documentation]  Ajoute un article au panier et vérifie le badge.
  [Tags]  add  feat:saucedemo.panier.ajout_article
  Open And Login As  STANDARD
  Add Product To Cart  ${TO_INVENTORY}[BTN_ADD_BACKPACK]
  Get Text  ${TO_INVENTORY}[LBL_CART_BADGE]  ==  1
```

Le test ne contient ni URL ni mot de passe : `Open And Login As` résout l'URL depuis
l'environnement actif et lit le secret désigné par le compte. Les locators vivent dans
`libraries/test_objects/`, les données attendues dans `libraries/test_data/`.

Les suites de `test_suites/multi_moteur/` vont un cran plus loin : elles sont écrites dans
un vocabulaire neutre et reçoivent leur adaptateur au lancement (`-v ACTIONS:`). Ajouter un
second moteur d'exécution revient à écrire un `actions_<moteur>.resource` — sans toucher
aux tests.

## Contrôles qualité

```bash
python tools/ci_local.py        # tout ce que joue la CI, en une commande
```

Tests unitaires Python, analyse statique Robot Framework, ESLint, tests et build du
frontend, audit des dépendances. Le workflow GitHub appelle **ce même script** : le local
et la CI ne peuvent pas diverger.

## Licence

MIT — voir [LICENSE](LICENSE).
