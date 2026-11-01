@echo off
setlocal
if /i "%CLAUDE_LEAN_COMMENTS%"=="off" exit /b 0
set "HOOK_SCRIPT=%~dp0..\%~1"
set "IS_PY3=import sys;sys.exit(sys.version_info<(3,))"
rem The version probe also rejects the Microsoft Store python3 stub, and nul keeps it off the hook payload.
py -3 -c "%IS_PY3%" <nul >nul 2>&1 && ( py -3 "%HOOK_SCRIPT%" & exit /b 0 )
python -c "%IS_PY3%" <nul >nul 2>&1 && ( python "%HOOK_SCRIPT%" & exit /b 0 )
python3 -c "%IS_PY3%" <nul >nul 2>&1 && ( python3 "%HOOK_SCRIPT%" & exit /b 0 )
echo lean-comments: Python 3 not found, so this hook did not run. Install Python 3 and add it to PATH. 1>&2
exit /b 1
