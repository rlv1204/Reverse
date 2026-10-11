@echo off
cd /d "%~dp0"
set PY=
where pyw >nul 2>nul && set PY=pyw
if not defined PY (where pythonw >nul 2>nul && set PY=pythonw)
if not defined PY (
  echo O Python nao foi encontrado. Rode primeiro o arquivo "instalar.cmd".
  pause
  exit /b 1
)
start "" %PY% gree.py gui
