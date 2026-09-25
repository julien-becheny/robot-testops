@ECHO OFF
SETLOCAL EnableDelayedExpansion

ECHO ================================================================================
ECHO        ROBOT-TESTOPS - INSTALLATION DE L'ENVIRONNEMENT
ECHO ================================================================================
ECHO.
ECHO Ce script :
ECHO   1. Cree l'environnement Python a l'identique du verrou (uv.lock)
ECHO   2. Initialise Playwright (navigateurs Chromium, Firefox, WebKit)
ECHO   3. Installe les dependances React (testops)
ECHO   4. Build le frontend TestOps
ECHO.
PAUSE

REM ── Verification des prerequis ──
WHERE uv >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    ECHO ❌ uv n'est pas installe : c'est lui qui gere Python et les dependances du projet.
    ECHO    Installez-le, puis rouvrez un terminal :
    ECHO        winget install --id=astral-sh.uv -e
    ECHO    Si winget est absent ou desactive :
    ECHO        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 ^| iex"
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
uv --version
node --version
npm --version
ECHO.

REM ── 1. Environnement Python ──
ECHO ────────────────────────────────────────────────────────────────
ECHO  ETAPE 1/4 : Environnement Python (uv sync)
ECHO ────────────────────────────────────────────────────────────────
ECHO  uv telecharge au besoin la version de Python indiquee par .python-version.

uv sync --locked
IF %ERRORLEVEL% NEQ 0 (
    ECHO ❌ Echec de la creation de l'environnement Python.
    PAUSE
    EXIT /B 1
)
ECHO ✅ Environnement Python conforme au verrou (outils qualite inclus).

CALL ".venv\Scripts\activate.bat"

REM ── 2. Initialisation Playwright (RF Browser) ──
ECHO.
ECHO ────────────────────────────────────────────────────────────────
ECHO  ETAPE 2/4 : Initialisation de Playwright (navigateurs)
ECHO ────────────────────────────────────────────────────────────────

python -m Browser.entry init
IF %ERRORLEVEL% NEQ 0 (
    ECHO ❌ Echec de l'initialisation de Playwright.
    ECHO    La version de robotframework-browser est verrouillee : verifiez l'acces
    ECHO    au registre npm, puis relancez setup.bat sans modifier cette version.
    PAUSE
    EXIT /B 1
)
ECHO ✅ Playwright initialise (Chromium, Firefox, WebKit).

REM ── 3. Installation des dependances frontend ──
ECHO.
ECHO ────────────────────────────────────────────────────────────────
ECHO  ETAPE 3/4 : Installation des dependances React/Vite (testops)
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

REM ── 4. Build du frontend ──
ECHO.
ECHO ─────────────────────────────────────────────────────────────
ECHO  ETAPE 4/4 : Build du frontend TestOps
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
python -c "import importlib.metadata as m; print('  ✅ AppiumLibrary:   ' + m.version('robotframework-appiumlibrary'))"
python -c "import flask; print(f'  ✅ Flask:            {flask.__version__}')"
python -c "import requests; print(f'  ✅ Requests:         {requests.__version__}')"

REM ── Verification mobile (Appium) - optionnel ──
ECHO.
ECHO ──────────────────────────────────────────────────────────
ECHO  MOBILE (APPIUM) - installation des drivers
ECHO ───────────────────────────────────────────────────────────

WHERE appium >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    ECHO  Installation du serveur Appium ^(npm -g^)...
    CALL npm install -g appium
) ELSE (
    ECHO  Serveur Appium deja present.
)

CALL appium driver list --installed 2>nul | findstr /C:"uiautomator2" >nul
IF %ERRORLEVEL% NEQ 0 (
    ECHO  Installation du driver Android uiautomator2...
    CALL appium driver install uiautomator2
) ELSE (
    ECHO  Driver uiautomator2 deja installe.
)

ECHO.
ECHO  A installer manuellement ^(hors npm^) :
ECHO      - Android SDK ^(Android Studio^) + ANDROID_HOME + platform-tools au PATH
ECHO      - iOS : un Mac ^(Xcode + driver xcuitest^)
ECHO.
python -m services.mobile.preflight

REM ── Tests de charge : Locust vient du verrou, k6 est un binaire externe ──
ECHO.
ECHO ────────────────────────────────────────────────────
ECHO  TESTS DE CHARGE - moteurs d'injection
ECHO ────────────────────────────────────────────────────
ECHO  Locust ^(modele ferme^) : installe par uv, rien a faire.
WHERE k6 >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    ECHO  k6 absent : les tests a DEBIT IMPOSE ne pourront pas demarrer.
    ECHO      Les autres types - smoke, load, stress, endurance, capacite, calibrage -
    ECHO      tournent avec Locust et ne le reclament pas.
    ECHO      Installation : winget install k6 --source winget
) ELSE (
    ECHO  k6 ^(modele ouvert^) deja present.
)

REM ── Outils qualite ──
ECHO.
ECHO ────────────────────────────────────────────
ECHO  OUTILS QUALITE ^(lint, analyse statique, tests^)
ECHO ────────────────────────────────────────────
ECHO  Installes par uv sync. Controles disponibles : uv run tools\ci_local.py

REM ── Creation des dossiers de sortie ──
IF NOT EXIST "%USERPROFILE%\rf_output\report" mkdir "%USERPROFILE%\rf_output\report"

CALL ".venv\Scripts\deactivate.bat"

ECHO.
ECHO ════════════════════════════════════════════════════════════════
ECHO                    INSTALLATION TERMINEE
ECHO ════════════════════════════════════════════════════════════════
ECHO.
ECHO 🚀 Pour demarrer :
ECHO    start_testops_windows.bat
ECHO    Interface TestOps : http://localhost:3000  -  API : http://localhost:5001
ECHO.
PAUSE
