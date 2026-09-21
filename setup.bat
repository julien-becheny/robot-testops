@ECHO OFF
SETLOCAL EnableDelayedExpansion

ECHO ================================================================================
ECHO        ROBOT-TESTOPS - INSTALLATION DE L'ENVIRONNEMENT
ECHO ================================================================================
ECHO.
ECHO Ce script :
ECHO   1. Cree un environnement virtuel Python
ECHO   2. Installe les packages Python (pip_requirements.txt)
ECHO   3. Initialise Playwright (navigateurs Chromium, Firefox, WebKit)
ECHO   4. Installe les dependances React (testops)
ECHO   5. Build le frontend TestOps
ECHO.
PAUSE

REM ── Verification des prerequis ──
WHERE python >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    ECHO ❌ Python n'est pas installe ou pas dans le PATH.
    ECHO    Installez Python 3.12+ depuis https://www.python.org/downloads/
    PAUSE
    EXIT /B 1
)

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)"
IF %ERRORLEVEL% NEQ 0 (
    ECHO ❌ Python 3.12+ est requis par les locks du projet.
    python --version
    PAUSE
    EXIT /B 1
)

WHERE node >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    ECHO ❌ Node.js n'est pas installe ou pas dans le PATH.
    ECHO    Installez Node.js 22.12+ depuis https://nodejs.org/
    PAUSE
    EXIT /B 1
)

FOR /F "tokens=1,2 delims=." %%A IN ('node -p "process.versions.node"') DO (
    SET "NODE_MAJOR=%%A"
    SET "NODE_MINOR=%%B"
)
SET "NODE_VERSION_OK=1"
IF !NODE_MAJOR! LSS 22 SET "NODE_VERSION_OK=0"
IF !NODE_MAJOR! EQU 22 IF !NODE_MINOR! LSS 12 SET "NODE_VERSION_OK=0"
IF "!NODE_VERSION_OK!" == "0" (
    ECHO ❌ Node.js 22.12+ est requis par Vite ^(version detectee : !NODE_MAJOR!.!NODE_MINOR!^).
    ECHO    Installez une version LTS recente depuis https://nodejs.org/
    PAUSE
    EXIT /B 1
)

REM ── Affichage des versions ──
ECHO.
ECHO 🔍 Versions detectees :
python --version
node --version
npm --version
ECHO.

REM ── 1. Environnement virtuel Python ──
ECHO ────────────────────────────────────────────────────────────────
ECHO  ETAPE 1/5 : Environnement virtuel Python
ECHO ────────────────────────────────────────────────────────────────

IF EXIST "env" (
    ECHO ⚠️  Un environnement virtuel existe deja.
    SET /P CONFIRM="Voulez-vous le recreer ? (O/N) : "
    IF /I "!CONFIRM!" == "O" (
        ECHO 🧹 Suppression de l'ancien environnement...
        CALL "env\Scripts\deactivate.bat" 2>nul
        rmdir /s /q env 2>nul
        IF EXIST "env" (
            ECHO ❌ Impossible de supprimer le dossier env.
            ECHO    Fermez tous les terminaux utilisant le venv et reessayez.
            PAUSE
            EXIT /B 1
        )
    ) ELSE (
        ECHO ✅ Conservation de l'environnement existant.
        GOTO ACTIVATE
    )
)

python -m venv env
IF NOT EXIST "env\Scripts\python.exe" (
    ECHO ❌ Echec de la creation du venv.
    PAUSE
    EXIT /B 1
)
ECHO ✅ Environnement virtuel cree.

:ACTIVATE
REM ── 2. Activation + Installation pip ──
ECHO.
ECHO ────────────────────────────────────────────────────────────────
ECHO  ETAPE 2/5 : Installation des packages Python
ECHO ────────────────────────────────────────────────────────────────

CALL "env\Scripts\activate.bat"
python -m pip install --upgrade pip --quiet

IF NOT EXIST "pip_requirements.txt" (
    ECHO ❌ pip_requirements.txt introuvable.
    PAUSE
    EXIT /B 1
)

python -m pip install -r pip_requirements.txt
IF %ERRORLEVEL% NEQ 0 (
    ECHO ❌ Echec de l'installation des packages Python.
    PAUSE
    EXIT /B 1
)
python -m pip check
IF %ERRORLEVEL% NEQ 0 (
    ECHO ❌ L'environnement Python contient des dependances incompatibles.
    PAUSE
    EXIT /B 1
)
ECHO ✅ Packages Python installes et verifies.

REM ── 3. Initialisation Playwright (RF Browser) ──
ECHO.
ECHO ────────────────────────────────────────────────────────────────
ECHO  ETAPE 3/5 : Initialisation de Playwright (navigateurs)
ECHO ────────────────────────────────────────────────────────────────

python -m Browser.entry init
IF %ERRORLEVEL% NEQ 0 (
    ECHO ❌ Echec de l'initialisation de Playwright.
    ECHO    La version Python est verrouillee : verifiez l'acces au registre npm,
    ECHO    puis relancez setup.bat sans mettre robotframework-browser a niveau.
    PAUSE
    EXIT /B 1
)
ECHO ✅ Playwright initialise (Chromium, Firefox, WebKit).

REM ── 4. Installation des dependances frontend ──
ECHO.
ECHO ────────────────────────────────────────────────────────────────
ECHO  ETAPE 4/5 : Installation des dependances React/Vite (testops)
ECHO ────────────────────────────────────────────────────────────────

IF NOT EXIST "testops\package.json" (
    ECHO ⚠️  Dossier testops non trouve, etape ignoree.
    GOTO VERIFY
)

PUSHD testops
CALL npm ci
IF %ERRORLEVEL% NEQ 0 (
    ECHO ❌ Echec de npm ci.
    POPD
    PAUSE
    EXIT /B 1
)
ECHO ✅ Dependances React/Vite installees.

REM ── 5. Build du frontend ──
ECHO.
ECHO ────────────────────────────────────────────────────────────────
ECHO  ETAPE 5/5 : Build du frontend TestOps
ECHO ────────────────────────────────────────────────────────────────

CALL npm run build
IF %ERRORLEVEL% NEQ 0 (
    ECHO ❌ Echec du build React.
    POPD
    PAUSE
    EXIT /B 1
)
POPD
ECHO ✅ Frontend TestOps compile.

:VERIFY
REM ── Verification finale ──
ECHO.
ECHO ════════════════════════════════════════════════════════════════
ECHO                    VERIFICATION FINALE
ECHO ════════════════════════════════════════════════════════════════

python -c "import robot; print(f'  ✅ Robot Framework: {robot.__version__}')"
python -c "import Browser; print(f'  ✅ RF Browser:      {Browser.__version__}')"
python -c "import flask; print(f'  ✅ Flask:            {flask.__version__}')"
python -c "import requests; print(f'  ✅ Requests:         {requests.__version__}')"

REM ── Outils qualite ──
ECHO.
ECHO ────────────────────────────────────────────
ECHO  OUTILS QUALITE ^(lint, analyse statique, tests^)
ECHO ────────────────────────────────────────────
python -m pip install -r pip_requirements-dev.txt --quiet
IF %ERRORLEVEL% NEQ 0 (
    ECHO ❌ Echec de l'installation des outils qualite.
    PAUSE
    EXIT /B 1
)
python -m pip check
IF %ERRORLEVEL% NEQ 0 (
    ECHO ❌ Les outils qualite ont introduit des dependances incompatibles.
    PAUSE
    EXIT /B 1
)
ECHO  Controles disponibles : python tools\ci_local.py

REM ── Creation des dossiers de sortie ──
IF NOT EXIST "%USERPROFILE%\rf_output\report" mkdir "%USERPROFILE%\rf_output\report"

CALL "env\Scripts\deactivate.bat"

ECHO.
ECHO ════════════════════════════════════════════════════════════════
ECHO                    INSTALLATION TERMINEE
ECHO ════════════════════════════════════════════════════════════════
ECHO.
ECHO 🚀 Pour demarrer :
ECHO    1. env\Scripts\activate
ECHO    2. python -m api.app
ECHO    3. Ouvrir http://localhost:5000 dans le navigateur
ECHO.
PAUSE
