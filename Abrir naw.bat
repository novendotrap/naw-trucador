@echo off
setlocal
title naw-trucador
set "naw_root=%~dp0"
cd /d "%naw_root%"
set "naw_action=open"
if "%NAW_SMOKE_TEST%"=="1" set "naw_action=smoke"
if not exist "%naw_root%app\launch.ps1" (
  echo [ERROR] Falta app\launch.ps1. Extrae el ZIP completo.
  set "naw_result=1"
  goto finish
)
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%naw_root%app\launch.ps1" %naw_action%
set "naw_result=%ERRORLEVEL%"
:finish
if "%naw_result%"=="0" goto success
echo.
echo No se completo la operacion. Revisa el error de arriba.
:success
if not "%naw_result%"=="0" if not "%NAW_NO_PAUSE%"=="1" pause
exit /b %naw_result%
