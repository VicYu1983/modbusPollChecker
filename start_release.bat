@echo off
setlocal

set "ROOT=%~dp0"
set "APP=%ROOT%ModbusPollChecker.exe"
if exist "%APP%" goto :launch

set "ROOT=%ROOT%build\release\ModbusPollChecker\"
set "APP=%ROOT%ModbusPollChecker.exe"
if not exist "%APP%" goto :app_missing

:launch
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $app=$env:APP; $root=$env:ROOT; $port=0; for ($candidate=8000; $candidate -le 8010; $candidate++) { $listener=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,$candidate); try { $listener.Start(); $listener.Stop(); $port=$candidate; break } catch { $listener.Stop() } }; if ($port -eq 0) { throw 'No available port between 8000 and 8010.' }; $env:MODBUS_PORT=[string]$port; $process=Start-Process -FilePath $app -WorkingDirectory $root -PassThru; $deadline=(Get-Date).AddSeconds(30); while ((Get-Date) -lt $deadline) { if ($process.HasExited) { throw 'Backend process exited during startup.' }; try { Invoke-RestMethod -Uri ('http://127.0.0.1:{0}/api/health' -f $port) -TimeoutSec 1 | Out-Null; Start-Process ('http://127.0.0.1:{0}' -f $port); exit 0 } catch {}; [System.Threading.Thread]::Sleep(500) }; throw 'Backend did not start within 30 seconds.'"
if errorlevel 1 (
	echo ERROR: The application did not start. Check the backend window for details.
	pause
	exit /b 1
)
exit /b 0

:app_missing
echo ERROR: ModbusPollChecker.exe was not found beside this file.
echo Run build_release.bat first, or run start.bat from the extracted release folder.
pause
exit /b 1