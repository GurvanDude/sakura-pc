param(
    [switch]$Uninstall,
    [string]$Python
)

$ErrorActionPreference = 'Stop'
$taskName = 'SakuraOptimizerHistory'
$userDir = Join-Path $env:APPDATA 'SakuraPC'
$stopFile = Join-Path $userDir 'history.stop'
$installLog = Join-Path $userDir 'optimizer-history-install.log'
$recorder = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'history_recorder.py'))

function Write-Journal([string]$Message) {
    if (-not (Test-Path -LiteralPath $userDir -PathType Container)) {
        New-Item -ItemType Directory -Path $userDir -Force | Out-Null
    }
    Add-Content -LiteralPath $installLog -Encoding UTF8 -Value ('{0} {1}' -f (Get-Date -Format s), $Message)
}

function Remove-HistoryTask {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($null -eq $task) { return }
    if ($task.State -eq 'Running') {
        Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    }
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host 'Lance-le dans un PowerShell normal.'
    exit 1
}

$actionText = if ($Uninstall) {
    "Sakura va arrêter l'historique et retirer sa tâche planifiée."
} else {
    "Sakura va installer l'historique pour ta session Windows."
}
Write-Host $actionText
if ((Read-Host 'Continuer ? (O/N)') -notmatch '^[OoYy]') {
    Write-Host "Rien n'a été modifié."
    exit 0
}

try {
    if ($Uninstall) {
        if (-not (Test-Path -LiteralPath $userDir -PathType Container)) {
            New-Item -ItemType Directory -Path $userDir -Force | Out-Null
        }
        New-Item -ItemType File -Path $stopFile -Force | Out-Null
        $limit = (Get-Date).AddSeconds(10)
        do {
            $running = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
            if ($null -eq $running -or $running.State -ne 'Running') { break }
            Start-Sleep -Milliseconds 250
        } while ((Get-Date) -lt $limit)
        Remove-HistoryTask
        Write-Journal "Enregistreur d'historique désinstallé."
        Write-Host "C'est désinstallé. L'historique déjà gardé sur le PC n'a pas été supprimé."
        exit 0
    }

    if (-not (Test-Path -LiteralPath $recorder -PathType Leaf)) {
        throw "history_recorder.py est introuvable à côté de cet installeur."
    }
    if ($Python) {
        $pythonExe = (Resolve-Path -LiteralPath $Python).Path
    } else {
        $pythonExe = (Get-Command python.exe -ErrorAction Stop).Source
    }
    $pythonw = if ([IO.Path]::GetFileName($pythonExe) -ieq 'pythonw.exe') {
        $pythonExe
    } else {
        Join-Path ([IO.Path]::GetDirectoryName($pythonExe)) 'pythonw.exe'
    }
    if (-not (Test-Path -LiteralPath $pythonw -PathType Leaf)) {
        throw "pythonw.exe est introuvable à côté de $pythonExe."
    }

    Remove-HistoryTask
    Remove-Item -LiteralPath $stopFile -Force -ErrorAction SilentlyContinue
    $arguments = '"{0}"' -f $recorder
    $action = New-ScheduledTaskAction -Execute $pythonw -Argument $arguments -WorkingDirectory ([IO.Path]::GetDirectoryName($recorder))
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity.Name
    $taskPrincipal = New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $taskPrincipal -Settings $settings -Force | Out-Null
    Start-ScheduledTask -TaskName $taskName
    Write-Journal "Enregistreur d'historique installé et démarré avec $pythonw."
    Write-Host "C'est installé ! L'historique démarre maintenant et à chaque ouverture de session."
} catch {
    Write-Journal ("Échec : " + $_.Exception.Message)
    Write-Host ("L'installation a échoué : " + $_.Exception.Message)
    Write-Host ('Consulte le journal : ' + $installLog)
    exit 1
}
