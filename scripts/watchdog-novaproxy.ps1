# watchdog-novaproxy.ps1 — jaga panel dan gateway novaproxy tetap hidup.
#
# Dua hal yang dijaga terpisah, karena beda sifatnya:
#   1. proses run.py (panel :12000) — kalau mati, dinyalakan.
#   2. gateway (:11500/:12500/:12501) — TIDAK menyala sendiri saat panel start,
#      jadi setelah panel hidup watchdog memanggil POST /api/gateway/start bila
#      salah satu port gateway kosong.
#
# Diperiksa tiap 60 detik. Jalankan sekali, atau daftarkan ke Task Scheduler:
#   schtasks /Create /TN "novaproxy-watchdog" /SC ONLOGON /RL HIGHEST ^
#     /TR "powershell -NoProfile -WindowStyle Hidden -File D:\Labs\novaproxy\scripts\watchdog-novaproxy.ps1"

$ErrorActionPreference = "Continue"

$root  = "D:\Labs\novaproxy"
$py    = "D:\Labs\novaproxy\.venv\Scripts\python.exe"
$log   = Join-Path $env:TEMP "opencode\watchdog-novaproxy.log"
$panel = 12000
$gw    = @(11500, 12500, 12501)

function Write-Log($msg) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    try { Add-Content -Path $log -Value $line -Encoding utf8 } catch { }
    Write-Output $line
}

function Test-Port($p) {
    return [bool](Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue)
}

function Ensure-Panel {
    if (Test-Port $panel) { return $true }
    try {
        Start-Process -FilePath $py -ArgumentList @("run.py") -WorkingDirectory $root `
            -WindowStyle Hidden -RedirectStandardError (Join-Path $env:TEMP "opencode\wd-np.err")
        Write-Log "panel 12000 mati -> dinyalakan"
    } catch {
        Write-Log ("panel gagal dinyalakan: {0}" -f $_.Exception.Message)
        return $false
    }
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Seconds 1
        if (Test-Port $panel) { return $true }
    }
    Write-Log "panel tidak mau listen setelah 20s"
    return $false
}

function Ensure-Gateway {
    foreach ($p in $gw) { if (Test-Port $p) { return } }
    try {
        Invoke-WebRequest -Uri "http://127.0.0.1:$panel/api/gateway/start" -Method POST `
            -ContentType "application/json" -Body "{}" -TimeoutSec 25 -UseBasicParsing | Out-Null
        Write-Log "gateway mati -> POST /api/gateway/start"
    } catch {
        Write-Log ("gateway gagal dinyalakan: {0}" -f $_.Exception.Message)
    }
}

Write-Log "watchdog novaproxy mulai (interval 60s, root=$root)"

while ($true) {
    if (Ensure-Panel) { Ensure-Gateway }
    Start-Sleep -Seconds 60
}
