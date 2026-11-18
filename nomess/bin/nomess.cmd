@echo off
rem Bare-command entry for agents that did not load a skill. Tries interpreters in fixed order, running a version check first
rem (without Python installed, python3 is a Store stub: the command exists but cannot run).
set "PY="
for %%P in ("py -3" python python3) do if not defined PY %%~P -c "import sys; sys.exit(sys.version_info < (3, 9))" >nul 2>nul && set "PY=%%~P"
if not defined PY (
  echo nomess: Python 3.9+ not found, tried: py -3, python, python3 1>&2
  exit /b 2
)
%PY% "%~dp0..\scripts\nomess.py" %*
exit /b %errorlevel%
