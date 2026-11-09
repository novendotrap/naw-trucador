@echo off
setlocal
title naw-trucador
set "naw_root=%~dp0"
cd /d "%naw_root%"
where py >nul 2>nul
if not errorlevel 1 (
  py -3.12 -c "import sys; assert sys.version_info[:2] == (3,12)" >nul 2>nul
  if not errorlevel 1 goto use_py
)
where python >nul 2>nul
if errorlevel 1 goto missing
python -c "import sys; assert sys.version_info[:2] == (3,12)" >nul 2>nul
if errorlevel 1 goto missing
python "%naw_root%app\bootstrap.py" install
set "naw_result=%ERRORLEVEL%"
goto finish
:use_py
py -3.12 "%naw_root%app\bootstrap.py" install
set "naw_result=%ERRORLEVEL%"
goto finish
:missing
echo [ERROR] Instala Python 3.12 de 64 bits y habilita Add Python to PATH.
echo https://www.python.org/downloads/windows/
set "naw_result=1"
:finish
if "%naw_result%"=="0" goto success
echo.
echo No se completo la operacion. Revisa el error de arriba.
:success
if not "%NAW_NO_PAUSE%"=="1" pause
exit /b %naw_result%
