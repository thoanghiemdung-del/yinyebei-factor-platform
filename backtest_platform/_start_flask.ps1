$env:DEEPSEEK_API_KEY = "sk-97e53fa7645849c9bf1679be75bc5eb8"
$proc = Start-Process -FilePath "python" `
    -ArgumentList @("-u", "app.py") `
    -WorkingDirectory "D:\yyb\backtest_platform" `
    -WindowStyle Hidden `
    -RedirectStandardOutput "D:\yyb\logs\app_stdout.log" `
    -RedirectStandardError "D:\yyb\logs\app_stderr.log" `
    -PassThru
Write-Host "Started Flask PID $($proc.Id)"
