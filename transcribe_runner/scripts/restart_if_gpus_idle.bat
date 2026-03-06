@echo off
setlocal enabledelayedexpansion
title Transcribe Runner - GPU idle restart (3060 only)

set CONTAINER_NAME=transcribe_runner
set THRESHOLD=30
set INTERVAL=60
set SHORT_INTERVAL=5
set MAX_CONSECUTIVE_RESTARTS=3
set RESTART_COUNT=0

rem Discover GPU indices whose name contains "3060" - write to temp file then read (pipe from nvidia-smi in for /f only returns 2 lines on Windows)
set GPU_IDS=
set "NVCSV=%TEMP%\nv_gpus_%RANDOM%.csv"
nvidia-smi --query-gpu=index,name --format=csv 2>&1 >"!NVCSV!"
for /f "skip=1 tokens=1* delims=," %%a in ('type "!NVCSV!"') do (
  set "idx=%%a"
  set "name=%%b"
  set "idx=!idx: =!"
  echo !name! | findstr /i "3060" >nul
  set "matched=0"
  if not errorlevel 1 set "matched=1"
  if !matched! equ 1 (
    if "!GPU_IDS!"=="" (set "GPU_IDS=!idx!") else (set "GPU_IDS=!GPU_IDS!,!idx!")
  )
)
if exist "!NVCSV!" del "!NVCSV!"

where nvidia-smi >nul 2>&1
if errorlevel 1 (
  echo nvidia-smi not found. Install NVIDIA drivers.
  pause
  exit /b 1
)
where docker >nul 2>&1
if errorlevel 1 (
  echo docker not found. Install Docker Desktop or Docker CLI.
  pause
  exit /b 1
)

if "!GPU_IDS!"=="" (
  echo [ERROR] No GPU with "3060" in name found. Exiting.
  pause
  exit /b 1
)

echo [INFO] Container: %CONTAINER_NAME%
echo [INFO] Monitoring 3060 GPUs only. GPU index/indices: %GPU_IDS%
echo [INFO] Threshold: %THRESHOLD% percent. If all 3060s stay below for 2 checks, restart. Max %MAX_CONSECUTIVE_RESTARTS% consecutive restarts then stop.
echo [INFO] Interval: %INTERVAL%s. Short recheck: %SHORT_INTERVAL%s.
echo [INFO] Press Ctrl+C to stop.
echo.

:loop
set "NOW=%date% %time%"
set "NOW=!NOW::=.!"
set ALL_IDLE_1=1
echo [CHECK1] !NOW! - 3060 GPU utilization (index %GPU_IDS%)
set IDX=0
for /f "delims=" %%a in ('nvidia-smi -i "!GPU_IDS!" --query-gpu=utilization.gpu --format="csv,noheader,nounits" 2^>nul') do (
  set "v=%%a"
  if "!v!"=="" set "v=0"
  if /i "!v!"=="N/A" set "v=0"
  set /a "vnum=!v!" 2>nul || set "v=0"
  echo   GPU index !IDX! = !v! percent
  if !v! GEQ %THRESHOLD% set ALL_IDLE_1=0
  set /a IDX+=1 >nul
)

if !ALL_IDLE_1! neq 1 goto not_idle

echo [CHECK1] !NOW! - All 3060 GPUs below %THRESHOLD% percent. Second check in %SHORT_INTERVAL%s...
timeout /t %SHORT_INTERVAL% /nobreak >nul

set ALL_IDLE_2=1
echo [CHECK2] !NOW! - 3060 GPU utilization
set IDX=0
for /f "delims=" %%a in ('nvidia-smi -i "!GPU_IDS!" --query-gpu=utilization.gpu --format="csv,noheader,nounits" 2^>nul') do (
  set "v=%%a"
  if "!v!"=="" set "v=0"
  if /i "!v!"=="N/A" set "v=0"
  set /a "vnum=!v!" 2>nul || set "v=0"
  echo   GPU index !IDX! = !v! percent
  if !v! GEQ %THRESHOLD% set ALL_IDLE_2=0
  set /a IDX+=1 >nul
)

if !ALL_IDLE_2! neq 1 goto second_check_busy
if !RESTART_COUNT! GEQ %MAX_CONSECUTIVE_RESTARTS% (
  echo [STOP] !NOW! - Already restarted %MAX_CONSECUTIVE_RESTARTS% times with no 3060 usage. Stopping restarts and exiting.
  pause
  exit /b 0
)
set /a RESTART_COUNT+=1
echo [ACTION] !NOW! - 3060 GPUs idle. Restarting %CONTAINER_NAME% (restart !RESTART_COUNT!/%MAX_CONSECUTIVE_RESTARTS%)...
docker restart %CONTAINER_NAME% || echo [ERROR] Failed to restart %CONTAINER_NAME%.
echo [INFO] Waiting %INTERVAL%s before next cycle...
timeout /t %INTERVAL% /nobreak >nul
goto end_choice

:second_check_busy
echo [CHECK2] !NOW! - Some 3060 GPU above %THRESHOLD% percent. No restart this cycle.
goto end_choice

:not_idle
set RESTART_COUNT=0
echo [CHECK1] !NOW! - Some 3060 GPU above %THRESHOLD% percent. No restart. Next check in %INTERVAL%s...
timeout /t %INTERVAL% /nobreak >nul

:end_choice
goto loop
