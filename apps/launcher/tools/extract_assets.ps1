# Copie les jaquettes Steam et extrait les icônes (256 px) des applis/jeux
# vers ui/assets. Lecture seule sur le système : n'écrit que dans le projet.
$root   = Split-Path $PSScriptRoot -Parent
$covers = Join-Path $root 'ui\assets\covers'
$icons  = Join-Path $root 'ui\assets\icons'
New-Item -ItemType Directory -Force $covers, $icons | Out-Null

Add-Type -AssemblyName System.Drawing
Add-Type @'
using System; using System.Runtime.InteropServices;
public static class IconX {
  [DllImport("user32.dll", CharSet=CharSet.Unicode)]
  public static extern uint PrivateExtractIcons(string file, int idx, int cx, int cy, IntPtr[] icons, uint[] ids, uint n, uint flags);
  [DllImport("user32.dll")] public static extern bool DestroyIcon(IntPtr h);
}
'@

function Save-Icon($src, $name) {
  $out = Join-Path $icons "$name.png"
  if ($src -like '*.png') { Copy-Item $src $out -Force; return }
  $h = [IntPtr[]]::new(1); $ids = [UInt32[]]::new(1)
  if ([IconX]::PrivateExtractIcons($src, 0, 256, 256, $h, $ids, 1, 0) -ge 1 -and $h[0] -ne [IntPtr]::Zero) {
    $bmp = [System.Drawing.Icon]::FromHandle($h[0]).ToBitmap()
    $bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose(); [IconX]::DestroyIcon($h[0]) | Out-Null
  } else { Write-Warning "Pas d'icône pour $name ($src)" }
}

# --- Jaquettes Steam
$lc = 'C:\Program Files (x86)\Steam\appcache\librarycache'
Get-ChildItem $lc -Directory | ForEach-Object {
  $f = Get-ChildItem $_.FullName -Recurse -Filter 'library_600x900.jpg' -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($f) { Copy-Item $f.FullName (Join-Path $covers "$($_.Name).jpg") -Force }
}

# --- Icônes des applis secondaires
# Prend la plus grande variante du logo (Square150x150Logo.scale-400.png, etc.)
$store = { param($n)
  Get-ChildItem (Join-Path (Get-AppxPackage -Name $n).InstallLocation 'Assets') -Filter 'Square150x150Logo*.png' -Recurse |
    Where-Object Name -notmatch 'contrast|altform' | Sort-Object Length -Descending | Select-Object -First 1 -ExpandProperty FullName }
$appIcons = @{
  spotify   = & $store 'SpotifyAB.SpotifyMusic'
  claude    = & $store 'Claude'
  discord   = "$env:LOCALAPPDATA\Discord\app.ico"
  operagx   = "$env:LOCALAPPDATA\Programs\Opera GX\opera.exe"
  vscode    = "$env:LOCALAPPDATA\Programs\Microsoft VS Code\Code.exe"
  flstudio  = 'C:\Program Files\Image-Line\FL Studio 2026\FL64.exe'
  wallpaper = 'C:\Program Files (x86)\Steam\steamapps\common\wallpaper_engine\wallpaper32.exe'
  # jeux hors Steam
  fortnite     = 'C:\Program Files\Epic Games\Fortnite\FortniteGame\Binaries\Win64\FortniteClient-Win64-Shipping.exe'
  rocketleague = 'C:\Program Files\Epic Games\rocketleague\Binaries\Win64\RocketLeague.exe'
  sonicmania   = 'C:\Program Files\Epic Games\SonicMania\SonicMania.exe'
  amongus      = 'C:\Program Files\Epic Games\AmongUs\Among Us.exe'
  cyberpunk    = 'C:\Program Files (x86)\GOG Galaxy\Games\Cyberpunk 2077\bin\x64\Cyberpunk2077.exe'
  azahar       = (Get-Command azahar -ErrorAction SilentlyContinue).Source
}
foreach ($k in $appIcons.Keys) {
  $p = $appIcons[$k]
  if ($p -and (Test-Path $p)) { Save-Icon $p $k } else { Write-Warning "Introuvable : $k ($p)" }
}
"Jaquettes : $((Get-ChildItem $covers).Count) | Icônes : $((Get-ChildItem $icons).Count)"
