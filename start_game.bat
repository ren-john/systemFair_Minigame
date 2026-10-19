@echo off
setlocal
cd /d "%~dp0"
set "GAME_PYTHON=%~dp0..\Model Training\venv\Scripts\python.exe"
if exist "%GAME_PYTHON%" goto run
set "GAME_PYTHON=%~dp0.venv\Scripts\python.exe"
if exist "%GAME_PYTHON%" goto run
echo Python environment not found. Follow the setup steps in README.md.
pause
exit /b 1
:run
"%GAME_PYTHON%" "%~dp0game.py" %*
if errorlevel 1 pause
endlocal
