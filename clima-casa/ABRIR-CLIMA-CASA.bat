@echo off
setlocal
cd /d "%~dp0"
call :acha_python
if not defined PY (
  echo O Python nao foi encontrado. Rode primeiro o arquivo INSTALAR.bat
  pause
  exit /b 1
)
set "PYW=%PY:python.exe=pythonw.exe%"
if not exist "%PYW%" set "PYW=%PY%"
set "APPDIR=%LOCALAPPDATA%\Programs\ClimaCasa"
if not exist "%APPDIR%\climacasa\__main__.py" set "APPDIR=%~dp0"
start "" /D "%APPDIR%" "%PYW%" -m climacasa
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
