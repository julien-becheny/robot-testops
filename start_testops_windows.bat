@echo off
setlocal

:: Configurer le code page en UTF-8
chcp 65001 >nul

:: Recuperer le dossier du script
set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"

echo ================================================================================
echo                    DEMARRAGE DE TESTOPS
echo                 Test Automation Control Panel
echo ================================================================================

set FLASK_HOST=0.0.0.0
set BROWSER=none

where uv >nul 2>&1
if errorlevel 1 (
    echo [!!] uv est introuvable dans le PATH - voir la section Demarrage du README.
    pause
    exit /b 1
)

:: Tuer les processus existants sur les ports 3000 et 5001
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":3000" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%P >nul 2>&1
)
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":5001" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%P >nul 2>&1
)

:: Demarrer le serveur Flask minimise
echo [..] Demarrage du serveur Flask sur %FLASK_HOST%:5001...
:: L'activation ne sert pas au lancement (uv s'en charge) mais a la RELANCE manuelle :
:: apres un Ctrl+C, `python api\app.py` vise alors le bon interpreteur, et le prompt le montre.
start /MIN "TestOps - Flask Server" cmd /k "cd /d "%ROOT%" && call .venv\Scripts\activate.bat & uv run python api\app.py"

:: Demarrer l'application React minimisee
echo [..] Demarrage de l'interface React...
start /MIN "TestOps - React App" cmd /k "cd /d "%ROOT%\testops" && npm start"

:: Attendre que le serveur React soit lance
echo [..] En attente du demarrage de TestOps...
echo     Veuillez patienter...

set ATTEMPTS=0
:CHECK_REACT
set /a ATTEMPTS+=1
if %ATTEMPTS% gtr 120 (
    echo [!!] Timeout: React n'a pas demarre apres 2 minutes.
    goto OPEN_BROWSER
)
powershell -NoProfile -Command "try { [Net.HttpWebRequest]::Create('http://localhost:3000').GetResponse() | Out-Null; exit 0 } catch { exit 1 }"
if %ERRORLEVEL% neq 0 (
    timeout /t 1 /nobreak >nul
    goto CHECK_REACT
)
echo [OK] React est pret !

:OPEN_BROWSER
:: Ouvrir dans Chrome (mode app) ou navigateur par defaut
set "CHROME_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe"
if exist "%CHROME_PATH%" (
    echo [OK] Ouverture dans Chrome...
    start "" "%CHROME_PATH%" --app="http://localhost:3000"
) else (
    echo [OK] Ouverture dans le navigateur par defaut...
    start "" "http://localhost:3000"
)

echo.
echo ================================================================================
echo                        TESTOPS DEMARRE
echo ================================================================================
echo Utilisez ces URL pour acceder aux services:
echo   - Interface utilisateur : http://localhost:3000
echo   - API Flask             : http://localhost:5001
echo.
echo Pour arreter tous les services, fermez les terminaux ouverts
echo ================================================================================

endlocal
