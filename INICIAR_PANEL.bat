@echo off
chcp 65001 >nul
title EMBEBIDOS_1 - Panel de Control
setlocal

REM ============================================================
REM   EMBEBIDOS_1 - Instalador + Panel de Control (un clic)
REM   - Crea el entorno virtual si no existe.
REM   - Instala dependencias (servidor + panel) la primera vez.
REM   - Abre el Panel de Control listo para usar.
REM ============================================================

REM Carpeta raiz = donde esta este .bat (sin la barra final).
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "SERVER_DIR=%ROOT%\Server_python_fastapi\face_server"
set "VENV=%SERVER_DIR%\.venv"
set "VENV_PY=%VENV%\Scripts\python.exe"
set "PANEL_DIR=%ROOT%\Panel_control_python"
set "PANEL=%PANEL_DIR%\app.py"
set "REQ_SERVER=%SERVER_DIR%\requirements.txt"
set "REQ_GUI=%PANEL_DIR%\requirements_gui.txt"
set "MARKER=%VENV%\.embebidos_deps_ok"

echo ============================================================
echo    EMBEBIDOS_1  -  Panel de Control
echo ============================================================
echo.

REM --- Validacion basica de la estructura ---
if not exist "%PANEL%" (
    echo ERROR: No se encontro el panel en:
    echo        "%PANEL%"
    echo        Ejecuta este .bat desde la carpeta del proyecto EMBEBIDOS_1.
    echo.
    pause
    exit /b 1
)

REM ------------------------------------------------------------
REM 1) Asegurar el entorno virtual de Python
REM ------------------------------------------------------------
if exist "%VENV_PY%" goto venv_ok

echo [1/3] Creando entorno virtual de Python...
set "BASEPY="
where py >nul 2>nul && set "BASEPY=py -3"
if defined BASEPY goto have_py
where python >nul 2>nul && set "BASEPY=python"
if defined BASEPY goto have_py
echo.
echo ERROR: No se encontro Python instalado.
echo        Instala Python 3.11 desde https://www.python.org/downloads/
echo        y marca la casilla "Add Python to PATH" durante la instalacion.
echo.
pause
exit /b 1

:have_py
%BASEPY% -m venv "%VENV%"
if errorlevel 1 (
    echo ERROR: No se pudo crear el entorno virtual.
    pause
    exit /b 1
)
echo     Entorno virtual creado.
goto deps

:venv_ok
echo [1/3] Entorno virtual: OK

REM ------------------------------------------------------------
REM 2) Instalar dependencias (solo la primera vez)
REM ------------------------------------------------------------
:deps
if exist "%MARKER%" goto deps_ok

echo [2/3] Instalando dependencias (la 1a vez puede tardar varios minutos)...
"%VENV_PY%" -m pip install --upgrade pip
"%VENV_PY%" -m pip install -r "%REQ_SERVER%"
if errorlevel 1 (
    echo ERROR instalando las dependencias del servidor.
    pause
    exit /b 1
)
"%VENV_PY%" -m pip install -r "%REQ_GUI%"
if errorlevel 1 (
    echo ERROR instalando las dependencias del panel.
    pause
    exit /b 1
)
>"%MARKER%" echo deps instaladas
echo     Dependencias instaladas.
goto launch

:deps_ok
echo [2/3] Dependencias: OK

REM ------------------------------------------------------------
REM 3) Abrir el Panel de Control
REM ------------------------------------------------------------
:launch
echo [3/3] Abriendo el Panel de Control...
echo.
echo     Dentro del panel: pulsa "Montar servidor" para iniciar todo.
echo     (Puedes minimizar esta ventana; cierrala al terminar.)
echo.
cd /d "%PANEL_DIR%"
"%VENV_PY%" "%PANEL%"
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
    echo.
    echo El panel se cerro con codigo %RC%. Revisa el mensaje de arriba.
    pause
)
endlocal
exit /b 0
