@echo off
setlocal

set "ROOT=%~dp0"

echo Starting Modbus Poll Checker backend...
start "Modbus Backend" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location -LiteralPath '%ROOT%backend'; python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

echo Starting Modbus Poll Checker frontend...
start "Modbus Frontend" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location -LiteralPath '%ROOT%frontend'; if (Get-Command pnpm -ErrorAction SilentlyContinue) { pnpm run dev -- --host 127.0.0.1 } else { npm run dev -- --host 127.0.0.1 }"

echo.
echo Backend:  http://127.0.0.1:8000
echo Frontend: http://127.0.0.1:5173
endlocal
