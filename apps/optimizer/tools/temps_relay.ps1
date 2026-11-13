$ErrorActionPreference = 'Stop'

$libraryDir = Join-Path $PSScriptRoot 'LibreHardwareMonitor'
$libraryPath = Join-Path $libraryDir 'LibreHardwareMonitorLib.dll'
$tempsFile = Join-Path $PSScriptRoot 'temps.json'
$stopFile = Join-Path $PSScriptRoot 'stop'
$logFile = Join-Path $PSScriptRoot 'temps.log'
$mutex = $null
$computer = $null
$ownsMutex = $false
$resolveHandler = $null
$lastErrors = @{}
$utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)

function Write-Journal([string]$Message, [string]$Level = 'INFO') {
    try {
        if ((Test-Path -LiteralPath $logFile -PathType Leaf) -and (Get-Item -LiteralPath $logFile).Length -gt 1MB) {
            [System.IO.File]::WriteAllText($logFile, '', $utf8WithoutBom)
        }
        $line = '{0} {1} {2}{3}' -f (Get-Date -Format s), $Level, $Message, [Environment]::NewLine
        [System.IO.File]::AppendAllText($logFile, $line, $utf8WithoutBom)
    } catch {
        # Le relais doit continuer même si son journal est momentanément indisponible.
    }
}

function Write-LimitedError([string]$Message) {
    $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    if (-not $lastErrors.ContainsKey($Message) -or $now - $lastErrors[$Message] -ge 60) {
        Write-Journal $Message 'ERREUR'
        $lastErrors[$Message] = $now
    }
}

function Get-HardwareTree($Hardware) {
    $Hardware.Update()
    Write-Output $Hardware
    foreach ($child in $Hardware.SubHardware) {
        Get-HardwareTree $child
    }
}

function Get-Sensors($Hardware, [string]$Type) {
    foreach ($sensor in $Hardware.Sensors) {
        if ([string]$sensor.SensorType -ne $Type -or $null -eq $sensor.Value) { continue }
        try {
            [pscustomobject]@{ Name = [string]$sensor.Name; Value = [double]$sensor.Value }
        } catch { continue }
    }
}

function Get-Preferred($Sensors, [string[]]$Names, [bool]$Fallback = $false) {
    foreach ($wanted in $Names) {
        foreach ($sensor in $Sensors) {
            if ($sensor.Name -eq $wanted) { return $sensor.Value }
        }
    }
    if ($Fallback -and $Sensors.Count -gt 0) { return $Sensors[0].Value }
    return $null
}

function Get-Temperature($Value) {
    if ($null -eq $Value) { return $null }
    try { $number = [double]$Value } catch { return $null }
    if ([double]::IsNaN($number) -or [double]::IsInfinity($number) -or $number -le 0 -or $number -gt 150) {
        return $null
    }
    return [Math]::Round($number, 1)
}

function Get-Positive($Value) {
    if ($null -eq $Value) { return $null }
    try { $number = [double]$Value } catch { return $null }
    if ([double]::IsNaN($number) -or [double]::IsInfinity($number) -or $number -le 0) { return $null }
    return [Math]::Round($number, 1)
}

function Read-Temperatures {
    $cpuTemperatures = @()
    $gpuTemperatures = @()
    $cpuClocks = @()
    $cpuPowers = @()
    foreach ($root in $computer.Hardware) {
        $kind = ([string]$root.HardwareType).ToLowerInvariant()
        $rootTemperatures = @()
        foreach ($hardware in @(Get-HardwareTree $root)) {
            $rootTemperatures += @(Get-Sensors $hardware 'Temperature')
            if ($kind.Contains('cpu')) {
                foreach ($sensor in @(Get-Sensors $hardware 'Clock')) {
                    if ($sensor.Name.StartsWith('Core #') -and $sensor.Value -gt 0) { $cpuClocks += $sensor.Value }
                }
                $cpuPowers += @(Get-Sensors $hardware 'Power')
            }
        }
        if ($kind.Contains('cpu')) { $cpuTemperatures += $rootTemperatures }
        elseif ($kind.Contains('gpu')) { $gpuTemperatures += $rootTemperatures }
    }

    $cpu = Get-Temperature (Get-Preferred $cpuTemperatures @('Core (Tctl/Tdie)', 'Tctl') $true)
    $gpu = Get-Temperature (Get-Preferred $gpuTemperatures @('GPU Core'))
    $hotspot = Get-Temperature (Get-Preferred $gpuTemperatures @('GPU Hot Spot'))
    $packagePower = Get-Preferred $cpuPowers @('Package')
    $clock = $null
    if ($cpuClocks.Count -gt 0) { $clock = Get-Positive (($cpuClocks | Measure-Object -Average).Average) }
    $reason = $null
    if ($null -eq $cpu) { $reason = 'température du processeur : il faut installer le lecteur de températures' }

    [ordered]@{
        cpu = $cpu
        gpu = $gpu
        gpu_hotspot = $hotspot
        cpu_clock_mhz = $clock
        cpu_power_w = Get-Positive $packagePower
        disks = @{}
        source = 'lecteur admin'
        reason = $reason
        time = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000.0
    }
}

function Write-Temperatures($Values) {
    $temporary = Join-Path $PSScriptRoot ('temps.{0}.tmp' -f [Guid]::NewGuid().ToString('N'))
    try {
        $json = $Values | ConvertTo-Json -Depth 4 -Compress
        [System.IO.File]::WriteAllText($temporary, $json, $utf8WithoutBom)
        if (Test-Path -LiteralPath $tempsFile -PathType Leaf) {
            # PowerShell transforme $null en "" : il faut NullString pour dire « pas de copie de sauvegarde »
            [System.IO.File]::Replace($temporary, $tempsFile, [System.Management.Automation.Language.NullString]::Value)
        } else {
            [System.IO.File]::Move($temporary, $tempsFile)
        }
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue }
    }
}

try {
    $createdNew = $false
    $mutex = New-Object System.Threading.Mutex($true, 'Global\SakuraOptimizerTemps', [ref]$createdNew)
    if (-not $createdNew) { exit 0 }
    $ownsMutex = $true
    Write-Journal 'Lecteur de températures démarré.'

    $resolveHandler = [ResolveEventHandler]{
        param($sender, $eventArgs)
        try {
            $simpleName = (New-Object Reflection.AssemblyName($eventArgs.Name)).Name
            $candidate = Join-Path $libraryDir ($simpleName + '.dll')
            if (Test-Path -LiteralPath $candidate -PathType Leaf) { return [Reflection.Assembly]::LoadFrom($candidate) }
        } catch { return $null }
        return $null
    }
    [AppDomain]::CurrentDomain.add_AssemblyResolve($resolveHandler)
    Add-Type -Path $libraryPath
    $computer = New-Object LibreHardwareMonitor.Hardware.Computer
    $computer.IsCpuEnabled = $true
    $computer.IsGpuEnabled = $true
    $computer.Open()

    while (-not (Test-Path -LiteralPath $stopFile)) {
        $started = [DateTime]::UtcNow
        try {
            $values = Read-Temperatures
            Write-Temperatures $values
            if ($values.reason) { Write-LimitedError ('Lecture incomplète : ' + $values.reason) }
        } catch {
            Write-LimitedError ('Erreur de lecture : ' + $_.Exception.Message)
        }
        $remaining = 2000 - ([DateTime]::UtcNow - $started).TotalMilliseconds
        if ($remaining -gt 0) { Start-Sleep -Milliseconds ([int]$remaining) }
    }
} catch {
    Write-LimitedError ('Erreur fatale : ' + $_.Exception.Message)
} finally {
    if ($null -ne $computer) {
        try { $computer.Close() } catch { Write-LimitedError ('Erreur à la fermeture : ' + $_.Exception.Message) }
    }
    if ($null -ne $resolveHandler) {
        try { [AppDomain]::CurrentDomain.remove_AssemblyResolve($resolveHandler) } catch {}
    }
    if ($ownsMutex -and $null -ne $mutex) { try { $mutex.ReleaseMutex() } catch {} }
    if ($null -ne $mutex) { $mutex.Dispose() }
    Remove-Item -LiteralPath $stopFile -Force -ErrorAction SilentlyContinue   # sinon il s'arrêterait au prochain démarrage
    Write-Journal 'Lecteur de températures arrêté.'
}
