@echo off
echo ===== AutoZAP Trading Signal System Installation =====
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Error: Python is not installed or not in PATH
    echo Please install Python 3.8 or newer and try again
    pause
    exit /b 1
)

echo Creating virtual environment...
python -m venv venv

echo Activating virtual environment...
call venv\Scripts\activate

echo Installing required packages...
pip install -r requirements.txt

echo.
echo Installation complete!
echo.
echo To start AutoZAP, run start.bat
echo.

pause
