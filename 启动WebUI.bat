@echo off
chcp 65001 >nul
title MediaCrawler WebUI 服务
echo ============================================
echo   MediaCrawler WebUI 服务启动
echo   Python: Hermes Runtime
echo   Port:   8081
echo   URL:    http://localhost:8081
echo ============================================
echo.

set PYTHONDONTWRITEBYTECODE=1

"C:\Users\JH\.hermes-web-ui\desktop-runtime\hermes\0.17.0\win-x64\python\python.exe" -m uvicorn api.main:app --host 0.0.0.0 --port 8081 --reload --app-dir "E:\codex\GitHub项目\MediaCrawler"

if errorlevel 1 (
    echo.
    echo 启动失败，请检查是否已有进程占用 8081 端口。
    pause
)
