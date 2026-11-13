param(
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
$taskName = 'SakuraTemps'
$sakuraDir = Join-Path $env:ProgramData 'SakuraPC'
$tempsDir = Join-Path $sakuraDir 'temps'
$installLog = Join-Path $sakuraDir 'install.log'
$relaySource = Join-Path $PSScriptRoot 'temps_relay.ps1'
$relayTarget = Join-Path $tempsDir 'temps_relay.ps1'
$stopFile = Join-Path $tempsDir 'stop'
$tempsFile = Join-Path $tempsDir 'temps.json'
$relayLog = Join-Path $tempsDir 'temps.log'
$archive = Join-Path $tempsDir 'LibreHardwareMonitor.zip'
$libraryDir = Join-Path $tempsDir 'LibreHardwareMonitor'
$downloadUrl = 'https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/download/v0.9.6/LibreHardwareMonitor.zip'
$expectedHash = '086d9f1b5a99e643edc2cfaaac16051685b551e4c5ac0b32a57c58c0e529c001'
$administratorsSid = '*S-1-5-32-544'
$systemSid = '*S-1-5-18'
$usersSid = '*S-1-5-32-545'

function Write-Journal([string]$Message) {
    if (-not (Test-Path -LiteralPath $sakuraDir -PathType Container)) {
        New-Item -ItemType Directory -Path $sakuraDir -Force | Out-Null
    }
    Add-Content -LiteralPath $installLog -Encoding UTF8 -Value ('{0} {1}' -f (Get-Date -Format s), $Message)
}

function Invoke-Icacls([string[]]$Arguments) {
    & (Join-Path $env:SystemRoot 'System32\icacls.exe') @Arguments | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Impossible de protéger $($Arguments[0]) (icacls : $LASTEXITCODE)." }
}

function Initialize-RealDirectory([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        $item = Get-Item -LiteralPath $Path -Force
        $isReparsePoint = ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
        if (-not $item.PSIsContainer -or $isReparsePoint) {
            if ($item.PSIsContainer) { [IO.Directory]::Delete($item.FullName) }
            else { [IO.File]::Delete($item.FullName) }
        }
    }
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Remove-Safely([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if ($null -eq $item) { return }
    $isReparsePoint = ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
    if ($isReparsePoint) {
        if ($item.PSIsContainer) { [IO.Directory]::Delete($item.FullName) }
        else { [IO.File]::Delete($item.FullName) }
        return
    }
    if ($item.PSIsContainer) {
        foreach ($child in @(Get-ChildItem -LiteralPath $item.FullName -Force)) {
            Remove-Safely $child.FullName
        }
        [IO.Directory]::Delete($item.FullName)
    } else {
        $item.Attributes = [IO.FileAttributes]::Normal
        [IO.File]::Delete($item.FullName)
    }
}

function Set-ProtectedDirectory([string]$Path, [switch]$Recursive) {
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
    $ownerArguments = @($Path, '/setowner', $administratorsSid, '/C', '/Q')
    $inheritanceArguments = @($Path, '/inheritance:r', '/C', '/Q')
    if ($Recursive) {
        $ownerArguments += '/T'
        $inheritanceArguments += '/T'
    }
    Invoke-Icacls $ownerArguments
    Invoke-Icacls $inheritanceArguments

    $items = @((Get-Item -LiteralPath $Path -Force))
    if ($Recursive) { $items += @(Get-ChildItem -LiteralPath $Path -Force -Recurse -ErrorAction Stop) }
    $admin = New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')
    $system = New-Object Security.Principal.SecurityIdentifier('S-1-5-18')
    $users = New-Object Security.Principal.SecurityIdentifier('S-1-5-32-545')
    foreach ($item in $items) {
        if ($item.PSIsContainer) { $acl = New-Object Security.AccessControl.DirectorySecurity }
        else { $acl = New-Object Security.AccessControl.FileSecurity }
        $acl.SetOwner($admin)
        $acl.SetAccessRuleProtection($true, $false)
        $inheritance = [Security.AccessControl.InheritanceFlags]::None
        if ($item.PSIsContainer) { $inheritance = [Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit' }
        $propagation = [Security.AccessControl.PropagationFlags]::None
        $allow = [Security.AccessControl.AccessControlType]::Allow
        $full = [Security.AccessControl.FileSystemRights]::FullControl
        $read = [Security.AccessControl.FileSystemRights]'ReadAndExecute, Synchronize'
        $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($admin, $full, $inheritance, $propagation, $allow)))
        $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($system, $full, $inheritance, $propagation, $allow)))
        $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($users, $read, $inheritance, $propagation, $allow)))
        Set-Acl -LiteralPath $item.FullName -AclObject $acl
    }
    $grantArguments = @($Path, '/grant:r', ($administratorsSid + ':(OI)(CI)F'), ($systemSid + ':(OI)(CI)F'), ($usersSid + ':(OI)(CI)RX'), '/C', '/Q')
    if ($Recursive) { $grantArguments += '/T' }
    Invoke-Icacls $grantArguments
}

function Stop-AndRemoveTask {
    $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($null -eq $task) { return }
    if ($task.State -eq 'Running') {
        Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        $limit = (Get-Date).AddSeconds(15)
        do {
            Start-Sleep -Milliseconds 250
            $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        } while ($null -ne $task -and $task.State -eq 'Running' -and (Get-Date) -lt $limit)
        if ($null -ne $task -and $task.State -eq 'Running') {
            throw "La tâche $taskName ne s'est pas arrêtée dans le délai prévu."
        }
    }
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
}

function Remove-TempsContents {
    foreach ($item in @(Get-ChildItem -LiteralPath $tempsDir -Force -ErrorAction SilentlyContinue)) {
        Remove-Safely $item.FullName
    }
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host 'Ouvre PowerShell en administrateur, puis relance cette commande.'
    exit 1
}

if ($Uninstall) {
    Write-Host 'Sakura va arrêter le lecteur de températures, retirer sa tâche planifiée et supprimer ses fichiers protégés.'
    if ((Read-Host 'Continuer ? (O/N)') -notmatch '^[OoYy]') {
        Write-Host "Rien n'a été modifié."
        exit 0
    }
    try {
        if (Test-Path -LiteralPath $tempsDir -PathType Container) { New-Item -ItemType File -Path $stopFile -Force | Out-Null }
        Stop-AndRemoveTask
        Write-Journal 'Lecteur de températures désinstallé.'
        if (Test-Path -LiteralPath $tempsDir) { Remove-Safely $tempsDir }
        if (Test-Path -LiteralPath $sakuraDir -PathType Container) {
            $remaining = @(Get-ChildItem -LiteralPath $sakuraDir -Force)
            if ($remaining.Count -eq 1 -and $remaining[0].Name -eq 'install.log') {
                Remove-Item -LiteralPath $sakuraDir -Recurse -Force
            }
        }
        Write-Host "C'est désinstallé. Le lecteur de températures et sa tâche planifiée ont été supprimés."
    } catch {
        Write-Journal ('Échec de la désinstallation : ' + $_.Exception.Message)
        Write-Host ('La désinstallation a échoué : ' + $_.Exception.Message)
        Write-Host ('Consulte le journal : ' + $installLog)
        exit 1
    }
    exit 0
}

Write-Host 'Sakura va installer un lecteur de températures protégé et ajouter sa tâche au démarrage de ta session.'
if ((Read-Host 'Continuer ? (O/N)') -notmatch '^[OoYy]') {
    Write-Host "Rien n'a été modifié."
    exit 0
}

try {
    if (-not (Test-Path -LiteralPath $relaySource -PathType Leaf)) {
        throw 'temps_relay.ps1 est introuvable à côté de cet installeur.'
    }
    Stop-AndRemoveTask
    Initialize-RealDirectory $sakuraDir
    Initialize-RealDirectory $tempsDir
    Set-ProtectedDirectory $sakuraDir
    Set-ProtectedDirectory $tempsDir
    # on ne garde dans SakuraPC que notre dossier et le journal (pas de jonction ni de fichier glissé par un autre)
    foreach ($item in @(Get-ChildItem -LiteralPath $sakuraDir -Force)) {
        $isLink = ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
        if ($item.Name -eq 'temps' -or ($item.Name -eq 'install.log' -and -not $isLink -and -not $item.PSIsContainer)) { continue }
        Remove-Safely $item.FullName
    }
    Remove-TempsContents

    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $downloadUrl -OutFile $archive -UseBasicParsing
    $actualHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $expectedHash) {
        Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue
        Write-Journal "Installation annulée : l'archive LibreHardwareMonitor a un SHA-256 inattendu ($actualHash)."
        Remove-Safely $tempsDir
        Write-Host "Installation annulée : le fichier téléchargé n'est pas la version attendue. Rien n'a été installé."
        Write-Host ('Consulte le journal : ' + $installLog)
        exit 1
    }

    New-Item -ItemType Directory -Path $libraryDir -Force | Out-Null
    Expand-Archive -LiteralPath $archive -DestinationPath $libraryDir -Force
    Remove-Item -LiteralPath $archive -Force
    Copy-Item -LiteralPath $relaySource -Destination $relayTarget -Force
    Set-ProtectedDirectory $sakuraDir -Recursive
    Set-ProtectedDirectory $tempsDir -Recursive

    $conhost = Join-Path $env:SystemRoot 'System32\conhost.exe'
    $powerShell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $arguments = '--headless "{0}" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{1}"' -f $powerShell, $relayTarget
    $action = New-ScheduledTaskAction -Execute $conhost -Argument $arguments -WorkingDirectory $tempsDir
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity.Name
    $taskPrincipal = New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType Interactive -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $taskPrincipal -Settings $settings -Force | Out-Null
    Start-ScheduledTask -TaskName $taskName
    Write-Journal 'Lecteur de températures installé et démarré.'

    $cpu = $null
    $limit = (Get-Date).AddSeconds(15)
    do {
        Start-Sleep -Milliseconds 500
        try {
            $sample = Get-Content -LiteralPath $tempsFile -Raw -ErrorAction Stop | ConvertFrom-Json
            $age = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000.0 - [double]$sample.time
            $candidate = [double]$sample.cpu
            if ($age -ge 0 -and $age -lt 10 -and $candidate -gt 0 -and $candidate -le 150) { $cpu = $candidate }
        } catch {}
    } while ($null -eq $cpu -and (Get-Date) -lt $limit)

    if ($null -ne $cpu) {
        Write-Host ("C'est installé ! Processeur : {0} °C." -f $cpu.ToString('0.#'))
    } else {
        Write-Host "C'est installé, mais la température du processeur n'est pas encore disponible."
        Write-Host ('Consulte le journal : ' + $relayLog)
    }
} catch {
    try { Stop-AndRemoveTask } catch {}
    Write-Journal ("Échec de l'installation : " + $_.Exception.Message)
    Write-Host ("L'installation a échoué : " + $_.Exception.Message)
    Write-Host ('Consulte le journal : ' + $installLog)
    exit 1
}
