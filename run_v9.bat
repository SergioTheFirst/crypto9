@echo off
chcp 65001 >nul

echo ===========================================
echo   Crypto Intel Premium v9 - FULL START
echo ===========================================

echo.
echo [1] Killing old processes...
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM redis-server.exe >nul 2>&1
echo     Done.
echo.

echo [2] Starting Redis...
cd /d C:\pro\crypto\crypto9\redis
start "" /min redis-server.exe redis.conf

echo     Waiting for Redis...
timeout /t 2 >nul

C:\pro\crypto\crypto9\redis\redis-cli.exe ping >nul 2>&1
if %errorlevel% NEQ 0 (
    echo     ERROR: Redis did not start!
    echo     Check: C:\pro\crypto\crypto9\redis\redis.log
    pause
    exit /b
)

echo     Redis is UP.
echo.

echo [3] Launching backend...
cd /d C:\pro\crypto\crypto9
python run_all.py

echo.
echo ===========================================
echo   Premium v9 stopped.
echo ===========================================
pause
