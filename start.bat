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

where yarn >nul 2>nul
if errorlevel 1 goto :node_missing

:check_frontend
if exist "%ROOT%frontend\node_modules\vite\bin\vite.js" goto :start_services

echo Installing frontend dependencies...
pushd "%ROOT%frontend"
if errorlevel 1 goto :frontend_install_failed
call yarn install --frozen-lockfile
if errorlevel 1 (
	popd
	goto :frontend_install_failed
)
popd
if not exist "%ROOT%frontend\node_modules\vite\bin\vite.js" goto :frontend_install_failed

:start_services

echo Starting Modbus Poll Checker backend...
start "Modbus Backend" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location -LiteralPath '%ROOT%backend'; python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

echo Starting Modbus Poll Checker frontend...
start "Modbus Frontend" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location -LiteralPath '%ROOT%frontend'; yarn dev --host 127.0.0.1"

echo Waiting for the frontend to become available...
start "" powershell -NoProfile -WindowStyle Hidden -Command "$url = 'http://127.0.0.1:5173'; $deadline = (Get-Date).AddSeconds(60); while ((Get-Date) -lt $deadline) { if (Test-NetConnection -ComputerName '127.0.0.1' -Port 5173 -InformationLevel Quiet -WarningAction SilentlyContinue) { Start-Process $url; exit }; Start-Sleep -Milliseconds 500 }; Start-Process $url"

echo.
echo Backend:  http://127.0.0.1:8000
echo Frontend: http://127.0.0.1:5173
exit /b 0

:python_missing
echo ERROR: Python was not found. Please install Python 3.10 or newer.
pause
exit /b 1

:node_missing
echo ERROR: Node.js and yarn were not found. Please install Node.js and Yarn.
pause
exit /b 1

:backend_install_failed
echo ERROR: Backend dependency installation failed.
pause
exit /b 1

:frontend_install_failed
echo ERROR: Frontend dependency installation failed or Vite is still missing.
echo Run yarn install in the frontend directory, then try again.
pause
exit /b 1
