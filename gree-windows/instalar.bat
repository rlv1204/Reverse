@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   Instalando o controle Gree local...
echo ============================================
echo.
set PY=
where py >nul 2>nul && set PY=py
if not defined PY (where python >nul 2>nul && set PY=python)
if not defined PY (
  echo [ERRO] O Python nao foi encontrado neste computador.
  echo.
  echo Instale o Python pelo site https://www.python.org/downloads/
  echo e MARQUE a opcao "Add python.exe to PATH" na primeira tela.
  echo Depois rode este arquivo de novo.
  echo.
  pause
  exit /b 1
)
%PY% -m pip install --upgrade -r requirements.txt
if errorlevel 1 (
  echo.
  echo [ERRO] A instalacao falhou. Verifique sua conexao com a internet e tente de novo.
  pause
  exit /b 1
)
echo.
echo Pronto! Agora de dois cliques em "abrir-gree.bat".
pause
