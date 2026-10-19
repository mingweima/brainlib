@echo off
rem Run brainlib on Windows from this folder. Nothing to install except Python 3.9 or newer.
setlocal
set PYTHONUTF8=1
set "HERE=%~dp0"
where py >nul 2>nul
if %ERRORLEVEL%==0 goto use_py
where python >nul 2>nul
if %ERRORLEVEL%==0 goto use_python
echo ERROR: Python 3.9 or newer was not found.
echo FIX: run "winget install -e --id Python.Python.3.12" or install Python 3.12 from the Microsoft Store, then open a new terminal and try again.
exit /b 2
:use_py
py -3 "%HERE%brainlib.py" %*
exit /b %ERRORLEVEL%
:use_python
python "%HERE%brainlib.py" %*
exit /b %ERRORLEVEL%
