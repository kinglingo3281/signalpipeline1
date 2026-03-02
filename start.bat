@echo off
echo ===== Starting AutoZAP Trading Signal System =====
echo.

REM Activate the virtual environment
echo Activating virtual environment...
call venv\Scripts\activate

echo Starting AutoZAP...
echo Press Ctrl+C to stop the system
echo.
python main.py --ui-port 5000

REM Deactivate the virtual environment when done
call deactivate
pause
