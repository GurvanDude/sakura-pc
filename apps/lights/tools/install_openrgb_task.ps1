# À lancer une fois dans PowerShell en administrateur : OpenRGB démarrera avec les droits administrateur
# (nécessaires pour piloter la RAM via PawnIO), à l'ouverture de session et sur demande du programme lumières.
$dir = Join-Path $PSScriptRoot 'OpenRGB\OpenRGB Windows 64-bit'
$action = New-ScheduledTaskAction -Execute (Join-Path $dir 'OpenRGB.exe') `
    -Argument '--localconfig --noautoconnect --server --server-port 6742' -WorkingDirectory $dir
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0 -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'SakuraOpenRGB' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Host 'Tâche SakuraOpenRGB installée.'
