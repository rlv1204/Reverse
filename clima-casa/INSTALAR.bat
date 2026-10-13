@echo off
setlocal
chcp 65001 >nul
title Clima Casa - Instalacao
cd /d "%~dp0"
echo.
echo  ================================================
echo     CLIMA CASA - instalacao
echo  ================================================
echo.
call :acha_python
if defined PY goto :tem_python

echo  [1/3] O Python nao esta instalado. Instalando agora...
echo        (pode aparecer uma janela pedindo permissao: clique em SIM)
echo.
winget install -e --id Python.Python.3.12 --scope user --accept-source-agreements --accept-package-agreements
call :acha_python
if defined PY goto :tem_python
echo.
echo  Nao foi possivel instalar o Python automaticamente.
echo  Siga o "Passo 2 - plano B" do arquivo LEIA-ME e depois rode este instalador de novo.
echo.
pause
exit /b 1

:tem_python
echo  [1/3] Python encontrado: %PY%
"%PY%" -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"
if errorlevel 1 (
  echo  Este Python e muito antigo. Instale o Python 3.12 ^(veja o LEIA-ME^).
  pause
  exit /b 1
)
echo.
echo  [2/3] Instalando o programa e criando o atalho "Clima Casa"...
echo        (se houver uma versao anterior, ela e substituida; suas configuracoes sao mantidas)
"%PY%" -m climacasa.instalar
if errorlevel 1 (
  echo.
  pause
  exit /b 1
)
echo.
echo  [3/3] Testando a rede e procurando os aparelhos Gree...
echo        Se o Windows perguntar sobre o Firewall, marque "Redes privadas" e clique em PERMITIR.
echo.
"%PY%" -m climacasa --diagnostico
echo.
echo  ================================================
echo   Pronto! O Clima Casa vai abrir agora.
echo   Depois, use o atalho "Clima Casa" na Area de Trabalho.
echo   A pasta extraida do zip ja pode ser apagada.
echo  ================================================
echo.
set "PYW=%PY:python.exe=pythonw.exe%"
if not exist "%PYW%" set "PYW=%PY%"
start "" /D "%LOCALAPPDATA%\Programs\ClimaCasa" "%PYW%" -m climacasa
pause
exit /b 0

:acha_python
set "PY="
for /f "delims=" %%i in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%i"
if defined PY goto :eof
for /f "delims=" %%i in ('python -c "import sys;print(sys.executable)" 2^>nul') do set "PY=%%i"
if defined PY goto :eof
for /d %%d in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%d\python.exe" set "PY=%%d\python.exe"
if defined PY goto :eof
for /d %%d in ("%ProgramFiles%\Python3*") do if exist "%%d\python.exe" set "PY=%%d\python.exe"
goto :eof
