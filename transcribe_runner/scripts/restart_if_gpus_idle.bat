@echo off
setlocal enabledelayedexpansion
title Transcribe Runner - GPU idle restart

set CONTAINER_NAME=transcribe_runner
set THRESHOLD=30
set INTERVAL=60
set SHORT_INTERVAL=5
rem Only monitor GPUs 1 and 2 (of 0,1,2) - transcribe uses these two only
set GPU_IDS=1 2

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

echo [INFO] Container: %CONTAINER_NAME%
echo [INFO] Threshold: %THRESHOLD%% GPU utilization
echo [INFO] Interval:         %INTERVAL%s between main cycles
echo [INFO] Short interval:   %SHORT_INTERVAL%s between double-checks when monitored GPUs are idle
echo [INFO] Monitoring GPUs: %GPU_IDS% only. Every %INTERVAL%s: if those GPUs ^< %THRESHOLD%%, wait %SHORT_INTERVAL%s and check again; if still ^< %THRESHOLD%%, restart %CONTAINER_NAME%.
echo [INFO] Press Ctrl+C to stop.
echo.

:loop
set ALL_IDLE_1=1
echo [CHECK1] %date% %time% - GPU utilization (monitoring GPUs %GPU_IDS%):
set IDX=0
for /f "skip=1 delims=" %%a in ('nvidia-smi --query-gpu=utilization.gpu --format=csv 2^>nul') do (
  set "v=%%a"
  set "v=!v: =!"
  set "v=!v:%%=!"
  if "!v!"=="" set "v=0"
  if /i "!v!"=="N/A" set "v=0"
  echo   GPU!IDX!: !v!%%
  if !IDX! equ 1 if !v! GEQ %THRESHOLD% set ALL_IDLE_1=0
  if !IDX! equ 2 if !v! GEQ %THRESHOLD% set ALL_IDLE_1=0
  set /a IDX+=1 >nul
)

if !ALL_IDLE_1! equ 1 (
  echo [CHECK1] %date% %time% - All GPUs below %THRESHOLD%%. Second check in %SHORT_INTERVAL%s...
  timeout /t %SHORT_INTERVAL% /nobreak >nul

  set ALL_IDLE_2=1
  echo [CHECK2] %date% %time% - GPU utilization (monitoring GPUs %GPU_IDS%):
  set IDX=0
  for /f "skip=1 delims=" %%a in ('nvidia-smi --query-gpu=utilization.gpu --format=csv 2^>nul') do (
    set "v=%%a"
    set "v=!v: =!"
    set "v=!v:%%=!"
    if "!v!"=="" set "v=0"
    if /i "!v!"=="N/A" set "v=0"
    echo   GPU!IDX!: !v!%%
    if !IDX! equ 1 if !v! GEQ %THRESHOLD% set ALL_IDLE_2=0
    if !IDX! equ 2 if !v! GEQ %THRESHOLD% set ALL_IDLE_2=0
    set /a IDX+=1 >nul
  )

  if !ALL_IDLE_2! equ 1 (
    echo [ACTION] %date% %time% - All GPUs still below %THRESHOLD%%. Restarting %CONTAINER_NAME%...
    docker restart %CONTAINER_NAME% || echo [ERROR] Failed to restart %CONTAINER_NAME%.
    echo [INFO] Waiting %INTERVAL%s before next main cycle...
    timeout /t %INTERVAL% /nobreak >nul
  ) else (
    echo [CHECK2] %date% %time% - Some GPU ^>= %THRESHOLD%% again. No restart this cycle.
  )
) else (
  echo [CHECK1] %date% %time% - Some GPU ^>= %THRESHOLD%%. No restart. Next check in %INTERVAL%s...
  timeout /t %INTERVAL% /nobreak >nul
)
goto loop
