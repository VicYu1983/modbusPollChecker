@echo off
setlocal

set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
set "BUILD_ROOT=%ROOT%build\release"
set "PYINSTALLER_DIST=%BUILD_ROOT%\pyinstaller-dist"
set "PACKAGE_DIR=%BUILD_ROOT%\ModbusPollChecker"
set "ARTIFACT_DIR=%ROOT%artifacts"
set "ARTIFACT_ZIP=%ARTIFACT_DIR%\ModbusPollChecker-windows-x64.zip"

if not exist "%PYTHON%" (
	where py >nul 2>nul
	if not errorlevel 1 (
		py -3 -m venv "%ROOT%.venv"
	) else (
		where python >nul 2>nul
		if errorlevel 1 goto :python_missing
		python -m venv "%ROOT%.venv"
	)
	if errorlevel 1 goto :venv_failed
)

echo Installing backend build dependencies...
"%PYTHON%" -m pip install -r "%ROOT%backend\requirements.txt"
if errorlevel 1 goto :backend_install_failed
"%PYTHON%" -m pip install pyinstaller
if errorlevel 1 goto :backend_install_failed

where node >nul 2>nul
if errorlevel 1 goto :node_missing
where npm >nul 2>nul
if errorlevel 1 goto :node_missing

if exist "%ROOT%frontend\node_modules" goto :frontend_ready
where pnpm >nul 2>nul
if not errorlevel 1 (
	pushd "%ROOT%frontend"
	call pnpm install --frozen-lockfile
	if errorlevel 1 (
		popd
		goto :frontend_install_failed
	)
	popd
) else (
	pushd "%ROOT%frontend"
	call npm install --no-package-lock
	if errorlevel 1 (
		popd
		goto :frontend_install_failed
	)
	popd
)

:frontend_ready
echo Building frontend...
pushd "%ROOT%frontend"
call npm run build
if errorlevel 1 (
	popd
	goto :frontend_build_failed
)
popd

if not exist "%ROOT%frontend\dist\index.html" goto :frontend_build_failed

echo Packaging backend...
"%PYTHON%" -m PyInstaller --noconfirm --clean --onedir --console ^
	--name ModbusPollChecker ^
	--distpath "%PYINSTALLER_DIST%" ^
	--workpath "%BUILD_ROOT%\pyinstaller-work" ^
	--specpath "%BUILD_ROOT%" ^
	--paths "%ROOT%backend" ^
	--collect-all pymodbus ^
	--add-data "%ROOT%frontend\dist;frontend\dist" ^
	--add-data "%ROOT%backend\app\repositories\migrations;app\repositories\migrations" ^
	"%ROOT%backend\run_app.py"
if errorlevel 1 goto :package_failed

if exist "%PACKAGE_DIR%" rmdir /s /q "%PACKAGE_DIR%"
mkdir "%PACKAGE_DIR%"
if errorlevel 1 goto :package_failed
xcopy "%PYINSTALLER_DIST%\ModbusPollChecker\*" "%PACKAGE_DIR%\" /e /i /y >nul
if errorlevel 1 goto :package_failed
copy /y "%ROOT%start_release.bat" "%PACKAGE_DIR%\start.bat" >nul
if errorlevel 1 goto :package_failed

if not exist "%ARTIFACT_DIR%" mkdir "%ARTIFACT_DIR%"
"%PYTHON%" -c "import shutil; shutil.make_archive(r'%ARTIFACT_DIR%\ModbusPollChecker-windows-x64', 'zip', r'%PACKAGE_DIR%')"
if errorlevel 1 goto :archive_failed
"%PYTHON%" -c "import sys, zipfile; sys.exit(0 if zipfile.is_zipfile(r'%ARTIFACT_ZIP%') else 1)"
if errorlevel 1 goto :archive_failed

echo.
echo Release package created:
echo   %ARTIFACT_ZIP%
echo Share this ZIP with coworkers. They should extract it and run start.bat.
pause
exit /b 0

:python_missing
echo ERROR: Install Python 3.10 or newer before building the release.
pause
exit /b 1

:venv_failed
echo ERROR: Could not create the build virtual environment.
pause
exit /b 1

:backend_install_failed
echo ERROR: Could not install backend build dependencies.
pause
exit /b 1

:node_missing
echo ERROR: Install Node.js 22 LTS before building the release.
pause
exit /b 1

:frontend_install_failed
echo ERROR: Could not install frontend dependencies.
pause
exit /b 1

:frontend_build_failed
echo ERROR: Frontend build failed.
pause
exit /b 1

:package_failed
echo ERROR: Backend packaging failed.
pause
exit /b 1

:archive_failed
echo ERROR: Could not create the release ZIP.
pause
exit /b 1