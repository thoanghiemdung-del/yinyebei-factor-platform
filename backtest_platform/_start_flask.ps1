$env:DEEPSEEK_API_KEY = "<SET_DEEPSEEK_API_KEY_IN_ENV>"
$proc = Start-Process -FilePath "python" `
    -ArgumentList @("-u", "app.py") `
    -WorkingDirectory "D:\yyb\backtest_platform" `
    -WindowStyle Hidden `
    -RedirectStandardOutput "D:\yyb\logs\app_stdout.log" `
    -RedirectStandardError "D:\yyb\logs\app_stderr.log" `
    -PassThru
Write-Host "Started Flask PID $($proc.Id)"

