param(
    [string]$Python,
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
$taskName = 'SakuraTemps'
$relay = (Resolve-Path (Join-Path $PSScriptRoot 'temps_relay.py')).Path
$sakuraDir = Join-Path $env:APPDATA 'SakuraPC'
$stopFile = Join-Path $sakuraDir 'temps.stop'
$logFile = Join-Path $sakuraDir 'optimizer-temps-task.log'

function Write-Journal([string]$Message) {
    New-Item -ItemType Directory -Path $sakuraDir -Force | Out-Null
    Add-Content -Path $logFile -Encoding UTF8 -Value "$(Get-Date -Format s) $Message"
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host 'Ouvre PowerShell en administrateur, puis relance cette commande.'
    exit 1
}

if ($Uninstall) {
    Write-Host 'Sakura va arrêter le lecteur de températures et retirer son démarrage automatique.'
    if ((Read-Host 'Continuer ? (O/N)') -notmatch '^[OoYy]') {
        Write-Host "Rien n'a été modifié."
        exit 0
    }
    New-Item -ItemType Directory -Path $sakuraDir -Force | Out-Null
    New-Item -ItemType File -Path $stopFile -Force | Out-Null
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Journal 'Lecteur de températures désinstallé.'
    Write-Host "C'est désinstallé. Le lecteur de températures va s'arrêter."
    exit 0
}

if ($Python) {
    $pythonExe = (Resolve-Path $Python).Path
} else {
    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not $command) {
        Write-Host 'Python est introuvable. Installe Python ou utilise -Python avec son chemin.'
        exit 1
    }
    $pythonExe = $command.Source
}
$pythonw = Join-Path (Split-Path $pythonExe) 'pythonw.exe'
if (-not (Test-Path $pythonw -PathType Leaf)) {
    Write-Host "pythonw.exe est introuvable à côté de python.exe."
    exit 1
}

Write-Host 'Sakura va ajouter le lecteur de températures au démarrage de ta session, avec les droits administrateur.'
if ((Read-Host 'Continuer ? (O/N)') -notmatch '^[OoYy]') {
    Write-Host "Rien n'a été modifié."
    exit 0
}

Remove-Item $stopFile -Force -ErrorAction SilentlyContinue
$action = New-ScheduledTaskAction -Execute $pythonw -Argument ('"' + $relay + '"') -WorkingDirectory (Split-Path $relay)
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$taskPrincipal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0 -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $taskPrincipal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Journal 'Lecteur de températures installé et démarré.'
Write-Host "C'est installé ! La température du processeur va apparaître dans Sakura Optimizer."
