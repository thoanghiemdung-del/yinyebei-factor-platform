# YYB Platform Restart — guarantees single instance, kills old processes properly
$ErrorActionPreference = "Continue"

Write-Host "=== Killing old processes ==="
$killed = 0
Get-Process python* -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine
        if ($cmd -match 'app\.py|lgb_worker|yyb_scheduler|combo_builder|corr_dedup|simple_miner|night_combo|yyb_guardian') {
            Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
            Write-Host "  Killed PID $($_.Id)"
            $killed++
        }
    } catch {}
}
Write-Host "Killed $killed process(es)"
Start-Sleep -Seconds 5

# Wait for port 5000 to be free
$retries = 0
while ($retries -lt 10) {
    $port = netstat -ano | Select-String ':5000.*LISTENING'
    if (-not $port) { break }
    Write-Host "Waiting for port 5000 to release..."
    Start-Sleep -Seconds 2
    $retries++
}

# Verify clean
$remaining = (Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'app\.py' }).Count
Write-Host "Remaining app.py: $remaining"

# Clean temp files
Remove-Item "$env:TEMP\lgb_task_*.json" -Force -ErrorAction SilentlyContinue
Remove-Item "$env:TEMP\task_*.json" -Force -ErrorAction SilentlyContinue

# Start Flask
$env:DEEPSEEK_API_KEY = "sk-97e53fa7645849c9bf1679be75bc5eb8"
$proc = Start-Process python -ArgumentList @("-u", "app.py") `
    -WorkingDirectory "D:\yyb\backtest_platform" `
    -WindowStyle Hidden `
    -RedirectStandardOutput "D:\yyb\logs\app_stdout.log" `
    -RedirectStandardError "D:\yyb\logs\app_stderr.log" `
    -PassThru
Write-Host "Started Flask PID $($proc.Id)"

# Wait for ready
for ($i=0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 3
    try {
        $code = (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:5000/login" -TimeoutSec 5).StatusCode
        if ($code -eq 200) { Write-Host "Flask READY (attempt $i)"; break }
    } catch {}
}

# Restart ngrok
Get-Process ngrok* -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 1
Start-Process "D:\yyb\ngrok.exe" -ArgumentList @("http","5000","--url=remark-glance-tweet.ngrok-free.dev","--pooling-enabled") -WindowStyle Hidden
Start-Sleep -Seconds 6
try {
    $code = (Invoke-WebRequest -UseBasicParsing -Uri "https://remark-glance-tweet.ngrok-free.dev/login" -TimeoutSec 15).StatusCode
    Write-Host "ngrok: $code"
} catch { Write-Host "ngrok: failed" }

# Final check
$count = (Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'app\.py' }).Count
Write-Host "Flask instances: $count (should be 1)"
Write-Host "DONE"
