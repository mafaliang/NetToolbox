@echo off
setlocal
cd /d "%~dp0"
echo ============================================
echo  NetToolbox v2.0 - Windows exe build script
echo ============================================
echo.
set "PY="
set "PYARGS="

rem 1) Try the python on PATH
call :TRY python
if defined PY goto :PY_READY

rem 2) Try the py launcher
py -3 -c "import tkinter" >NUL 2>&1
if not errorlevel 1 (
    set "PY=py"
    set "PYARGS=-3"
)
if defined PY goto :PY_READY

rem 3) Try common installation directories
for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "C://Python313//python.exe"
    "C://Python312//python.exe"
) do (
    if not defined PY if exist %%P call :TRY %%P
)

rem 4) Try uv-managed CPython installations
for /d %%D in ("%APPDATA%\uv\python\cpython-*") do (
    if not defined PY if exist "%%D\python.exe" call :TRY "%%D\python.exe"
)

:PY_READY
if not defined PY (
    echo [ERROR] No Python 3.8+ with tkinter was found.
    pause
    exit /b 1
)

echo Using interpreter: "%PY%" %PYARGS%
"%PY%" %PYARGS% --version

echo [1/3] Check PyInstaller ...
"%PY%" %PYARGS% -c "import PyInstaller" >NUL 2>&1
if errorlevel 1 (
    "%PY%" %PYARGS% -m pip install pyinstaller
    if errorlevel 1 (
        echo [WARN] Retrying with --break-system-packages ...
        "%PY%" %PYARGS% -m pip install --break-system-packages pyinstaller
    )
)
"%PY%" %PYARGS% -c "import PyInstaller" >NUL 2>&1
if errorlevel 1 (
    echo [ERROR] Failed to install PyInstaller.
    pause
    exit /b 1
)

echo [2/3] Building, please wait ...
"%PY%" %PYARGS% -m PyInstaller -F -w --clean -n NetToolbox main.py
if errorlevel 1 (
    echo [ERROR] Build failed. Check PyInstaller logs above.
    pause
    exit /b 1
)

echo [3/3] Done.
echo.
echo Output: dist\NetToolbox.exe
echo.
pause
exit /b 0

:TRY
set "CAND=%~1"
"%CAND%" -c "import tkinter" >NUL 2>&1
if errorlevel 1 exit /b 0
set "PY=%CAND%"
set "PYARGS="
exit /b 0
