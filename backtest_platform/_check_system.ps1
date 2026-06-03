# System health check
$os = Get-CimInstance Win32_OperatingSystem
$totalGB = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
$freeGB = [math]::Round($os.FreePhysicalMemory / 1MB, 1)
$usedGB = [math]::Round(($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) / 1MB, 1)
Write-Host "Memory: Total=${totalGB}GB, Free=${freeGB}GB, Used=${usedGB}GB"

# Python processes
Write-Host "`nPython processes:"
Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' } | ForEach-Object {
    Write-Host "  PID $($_.ProcessId): $($_.CommandLine)"
}

# Check for specific processes
Write-Host "`nSpecific process check:"
$patterns = @('yyb_scheduler_loop', 'combo_builder', 'simple_miner', 'app.py', 'lgb_worker')
foreach ($p in $patterns) {
    $found = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match $p }
    if ($found) {
        foreach ($f in $found) {
            Write-Host "  [$p] PID $($f.ProcessId)"
        }
    } else {
        Write-Host "  [$p] NOT running"
    }
}

# Check Python bitness
Write-Host "`nPython architecture:"
& "python" -c "import struct; print(struct.calcsize('P') * 8, 'bit'); import numpy; print('numpy', numpy.__version__)"
