@echo off
chcp 65001 >nul

:: Try Chinese path first
if exist "E:\codex\GitHub项目\MediaCrawler" (
  cd /d "E:\codex\GitHub项目\MediaCrawler"
) else (
  :: Fallback: check if the E: drive mapping is different
  echo [ERROR] Project directory not found
  echo Please edit this batch file and update the PROJECT_DIR path.
  pause
  exit /b 1
)

echo [1/3] Starting server...
start "MediaCrawler" cmd /k "uv run python -m api.main"

echo [2/3] Waiting...
ping -n 4 127.0.0.1 >nul

echo [3/3] Opening Dashboard...
start http://localhost:8080

echo.
echo MediaCrawler started! Dashboard: http://localhost:8080
echo.
timeout /t 5 /nobreak >nul
exit
