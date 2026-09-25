@echo off
setlocal

set "ROOT=%~dp0"

where python >nul 2>nul
if errorlevel 1 goto :python_missing
python -c "import fastapi, pymodbus, uvicorn" >nul 2>nul
if errorlevel 1 (
	echo Installing backend dependencies...
	python -m pip install -r "%ROOT%backend\requirements.txt"
	if errorlevel 1 goto :backend_install_failed
)

where pnpm >nul 2>nul
if not errorlevel 1 goto :frontend_ready
where npm >nul 2>nul
if errorlevel 1 goto :node_missing

:frontend_ready
if exist "%ROOT%frontend\node_modules" goto :start_services
echo Frontend dependencies are missing. Run pnpm install or npm install in frontend first.
goto :frontend_install_failed

:start_services

echo Starting Modbus Poll Checker backend...
start "Modbus Backend" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location -LiteralPath '%ROOT%backend'; python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

echo Starting Modbus Poll Checker frontend...
start "Modbus Frontend" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location -LiteralPath '%ROOT%frontend'; if (Get-Command pnpm -ErrorAction SilentlyContinue) { pnpm run dev -- --host 127.0.0.1 } else { npm run dev -- --host 127.0.0.1 }"

echo.
echo Backend:  http://127.0.0.1:8000
echo Frontend: http://127.0.0.1:5173
exit /b 0

:python_missing
echo ERROR: Python was not found. Please install Python 3.10 or newer.
pause
exit /b 1

:node_missing
echo ERROR: Node.js and pnpm were not found. Please install Node.js.
pause
exit /b 1

:backend_install_failed
echo ERROR: Backend dependency installation failed.
pause
exit /b 1

:frontend_install_failed
echo ERROR: Frontend dependencies are missing. Run pnpm install or npm install in frontend first.
pause
exit /b 1
