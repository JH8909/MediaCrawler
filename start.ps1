# MediaCrawler One-Click Launcher (PowerShell)
$projectDir = "E:\codex\GitHub项目\MediaCrawler"

if (-not (Test-Path $projectDir)) {
    Write-Host "[ERROR] Cannot find project directory" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Set-Location $projectDir

Write-Host "[1/3] Starting server..." -ForegroundColor Yellow
Start-Process -FilePath "uv" -ArgumentList "run python -m api.main" -WorkingDirectory $projectDir -WindowStyle Normal

Start-Sleep -Seconds 3

Write-Host "[2/3] Opening Dashboard..." -ForegroundColor Yellow
Start-Process "http://localhost:8080"

Write-Host "[3/3] Done!"
Write-Host "Dashboard: http://localhost:8080" -ForegroundColor Green
Read-Host "Press Enter to exit"
