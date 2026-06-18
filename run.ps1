# ============================================================
#  SLMP PLC vezérlő — frissítés + indítás (Windows PowerShell)
#
#  1) Megnézi a GitHubon a legújabb commit SHA-t, és csak akkor
#     tölt le, ha változott (current_version.txt-hez hasonlítva).
#  2) Kicsomagolja, és az alkalmazás fájljait frissíti
#     (a start.bat bootstrap-ot szándékosan NEM írja felül).
#  3) Telepíti a függőségeket (csak ha hiányoznak), majd indít
#     és megnyitja a böngészőt.
#
#  Nem kell hozzá sem "gh", sem "git" — csak a Windowsban
#  alapból meglévő PowerShell. Internet hiányában a legutóbb
#  letöltött (helyi) verzió indul.
# ============================================================

$ErrorActionPreference = 'Stop'

# Windows PowerShell 5.1 alapból nem TLS 1.2-t használ -> a GitHub elutasítaná.
[Net.ServicePointManager]::SecurityProtocol = `
    [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$Repo    = 'CoolFrog2/SLMP'
$Branch  = 'master'
$Root    = $PSScriptRoot
$Headers = @{ 'User-Agent' = 'SLMP-updater' }

function Find-Python {
    foreach ($c in @('py', 'python', 'python3')) {
        if (Get-Command $c -ErrorAction SilentlyContinue) { return $c }
    }
    return $null
}

# ---------- 1-2) Frissítés GitHubról ----------
try {
    Write-Host "Frissites ellenorzese ($Repo)..." -ForegroundColor Cyan
    $latest  = (Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/commits/$Branch" -Headers $Headers -TimeoutSec 10 -UseBasicParsing).sha
    $verFile = Join-Path $Root 'current_version.txt'
    $current = if (Test-Path $verFile) { (Get-Content $verFile -Raw).Trim() } else { '' }

    if ($latest -eq $current) {
        Write-Host ("Mar a legujabb verzio (commit {0})." -f $latest.Substring(0,7)) -ForegroundColor Green
    }
    else {
        Write-Host ("Uj verzio elerheto: {0} -- letoltes..." -f $latest.Substring(0,7)) -ForegroundColor Yellow
        $zip = Join-Path $env:TEMP 'slmp_update.zip'
        $dir = Join-Path $env:TEMP 'slmp_update'
        Invoke-WebRequest -Uri "https://codeload.github.com/$Repo/zip/refs/heads/$Branch" -OutFile $zip -Headers $Headers -TimeoutSec 60 -UseBasicParsing
        if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
        Expand-Archive -Path $zip -DestinationPath $dir -Force

        $src = (Get-ChildItem -Path $dir -Directory | Select-Object -First 1).FullName
        Get-ChildItem -Path $src -Recurse -File | ForEach-Object {
            $rel = $_.FullName.Substring($src.Length + 1)
            if ($rel -ieq 'start.bat') { return }   # a bootstrap-ot nem bantjuk
            $dest = Join-Path $Root $rel
            $destDir = Split-Path $dest -Parent
            if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }
            Copy-Item -Path $_.FullName -Destination $dest -Force
        }
        Set-Content -Path $verFile -Value $latest
        Remove-Item $zip -Force -ErrorAction SilentlyContinue
        Remove-Item $dir -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host ("Frissitve a(z) {0} verziora." -f $latest.Substring(0,7)) -ForegroundColor Green
    }
}
catch {
    Write-Warning ("Frissites kihagyva (nincs internet vagy GitHub elerhetetlen): {0}" -f $_.Exception.Message)
    Write-Host "A helyi (legutobb letoltott) verzio indul." -ForegroundColor DarkGray
}

# ---------- Python ----------
$py = Find-Python
if (-not $py) {
    Write-Host ""
    Write-Host "[HIBA] Nincs telepitett Python." -ForegroundColor Red
    Write-Host "Toltsd le innen: https://www.python.org/downloads/" -ForegroundColor Red
    Write-Host "Telepiteskor pipald be az 'Add Python to PATH' opciot." -ForegroundColor Red
    exit 1
}

# ---------- Függőségek (csak ha hiányoznak) ----------
& $py -c "import flask" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Fuggosegek telepitese (flask)..." -ForegroundColor Cyan
    & $py -m pip install --disable-pip-version-check -r (Join-Path $Root 'requirements.txt')
}

# ---------- Indítás ----------
Write-Host ""
Write-Host "SLMP PLC vezerlo indul: http://localhost:5000" -ForegroundColor Cyan
Write-Host "(A leallitashoz zard be ezt az ablakot vagy nyomj Ctrl+C-t.)" -ForegroundColor DarkGray

# böngésző megnyitása kis késleltetéssel, mire a szerver feláll
Start-Process powershell -WindowStyle Hidden -ArgumentList @(
    '-NoProfile', '-Command',
    'Start-Sleep -Seconds 2; Start-Process "http://localhost:5000"'
)

& $py (Join-Path $Root 'app.py')
