@echo off
setlocal ENABLEDELAYEDEXPANSION

TITLE Crypto Intel Premium v9 - MASTER START

echo ===========================================
echo   Crypto Intel Premium v9 - FULL START
echo ===========================================
echo.

REM ---------------------------------------------------
REM 1. Kill previous processes
REM ---------------------------------------------------
echo [1] Killing old processes...
taskkill /F /IM redis-server.exe >nul 2>&1
taskkill /F /IM python.exe >nul 2>&1
echo     Done.
echo.

REM ---------------------------------------------------
REM 2. Start Redis server (ONLY from correct folder)
REM ---------------------------------------------------
echo [2] Starting Redis...

cd /d C:\pro\crypto\crypto9\redis
start "" /MIN redis-server.exe redis.conf

echo     Waiting for Redis...

REM Wait until port 6379 is open
:wait_redis
powershell -command "try { (New-Object Net.Sockets.TcpClient('127.0.0.1',6379)).Close(); exit 0 } catch { exit 1 }"

if %errorlevel% neq 0 (
    ping 127.0.0.1 -n 2 >nul
    goto wait_redis
)

echo     Redis is UP.
echo.

REM ---------------------------------------------------
REM 3. Start backend
REM ---------------------------------------------------

echo [3] Launching backend...
cd /d C:\pro\crypto\crypto9

REM Clear screen separation
echo ----------------------------------------------------

REM Start backend directly inside console (no secondary window)
python run_all.py

echo ----------------------------------------------------
echo [4] Backend SHUTDOWN.
echo.
echo Press any key to kill Redis and exit...
pause >nul

REM ---------------------------------------------------
REM 4. Cleanup
REM ---------------------------------------------------
taskkill /F /IM redis-server.exe >nul 2>&1

endlocal