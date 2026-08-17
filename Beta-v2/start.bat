@echo off
setlocal
set "BETA_DIR=%~dp0"
set "BETA_PYTHON=%BETA_DIR%.venv\Scripts\python.exe"

if not exist "%BETA_PYTHON%" (
    echo [ERROR] Beta-v2 virtual environment is missing. Follow README.md first-time setup.
    exit /b 1
)

"%BETA_PYTHON%" "%BETA_DIR%run.py"
exit /b %ERRORLEVEL%
