# OpenAver Windows 安裝程式
# 設計重點：
#   1. 解壓不依賴 Microsoft.PowerShell.Archive 模組（Expand-Archive）
#      —— 改用 .NET ZipFile 逐 entry 解壓，相容 Windows Sandbox / 精簡映像。
#   2. 自動偵測並靜默安裝 Microsoft Edge WebView2 Runtime（缺它必開不了）。
#   3. 強制 TLS 1.2，相容預設停用 TLS1.2 的乾淨系統。
#   4. 偵測 OpenAver 是否執行中（下載前提早擋 + 清舊版時 retry），提醒關閉、不強殺。
#   5. zip-slip 防護：entry 必須落在安裝目錄內。
$ErrorActionPreference = "Stop"
$Repo = "slive777/OpenAver"
$InstallDir = "$HOME\OpenAver"

# 乾淨映像 / 舊系統的 PowerShell 5.1 預設可能用 TLS1.0，GitHub 會拒連
try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}

Write-Host ""
Write-Host "=============================="
Write-Host "   OpenAver 安裝程式"
Write-Host "=============================="
Write-Host ""

# ============ 工具函數 ============

# 不依賴 Expand-Archive 的解壓（逐 entry，覆蓋既有檔）
# 為何不用 [ZipFile]::ExtractToDirectory($zip,$dest,$true)：3 參數多載只在 .NET Core，
# PS 5.1 = .NET Framework 4.x 沒有 → 覆蓋既有安裝會 throw。ExtractToFile 4.5+ 即有。
function Expand-ZipRobust {
    param([string]$ZipPath, [string]$Destination, [string]$ConfineTo)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    # zip-slip 防護：每個 entry 解出的目標路徑必須留在 $ConfineTo 底下（= 安裝目錄
    # ~\OpenAver），否則惡意 release asset 不只能用 ..\ 往上逃，連 entry 不帶
    # OpenAver/ 前綴（如 Desktop\evil.bat）也會寫到安裝目錄外、卻仍在 $HOME 內。
    # 故邊界收緊到 $ConfineTo 而非解壓基準 $Destination($HOME)。
    # 尾端補分隔再比，避免目錄 entry 自身被誤殺、以及 OpenAverEvil\ 這類前綴假陽性。
    $confine = [System.IO.Path]::GetFullPath($ConfineTo).TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
    $zip = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        foreach ($entry in $zip.Entries) {
            $rel = $entry.FullName -replace '/', '\'
            $target = Join-Path $Destination $rel
            $full = [System.IO.Path]::GetFullPath($target)
            $probe = $full.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
            if (-not $probe.StartsWith($confine, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "ZIP entry 逸出安裝目錄（已中止）: $($entry.FullName)"
            }
            if ([string]::IsNullOrEmpty($entry.Name)) {
                # 目錄 entry（FullName 以 / 結尾）
                New-Item -ItemType Directory -Path $full -Force | Out-Null
                continue
            }
            $parent = Split-Path $full -Parent
            if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
            [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $full, $true)
        }
    } finally {
        $zip.Dispose()
    }
}

# 偵測 WebView2 Runtime 是否已安裝（HKLM 64/32 + HKCU per-user）
function Test-WebView2 {
    $guid = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
    $paths = @(
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\$guid",
        "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\$guid",
        "HKCU:\SOFTWARE\Microsoft\EdgeUpdate\Clients\$guid"
    )
    foreach ($p in $paths) {
        try {
            $pv = (Get-ItemProperty -Path $p -Name pv -ErrorAction Stop).pv
            if ($pv -and $pv -ne '0.0.0.0') { return $true }
        } catch {}
    }
    return $false
}

# 偵測 OpenAver 是否正在執行（有 process 的執行檔路徑落在安裝目錄底下）
# 自家 app 以當前 user 身分跑，pythonw.exe 的 .Path 可讀；他人 process 的
# .Path 會丟 UnauthorizedAccessException，內層 try 吞掉視為非 OpenAver。
function Test-OpenAverRunning {
    param([string]$Dir)
    $root = $Dir.TrimEnd('\') + '\'
    $procs = Get-Process -ErrorAction SilentlyContinue | Where-Object {
        try { $_.Path -and $_.Path.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase) } catch { $false }
    }
    return [bool]$procs
}

# 提醒用戶關閉 OpenAver 並等待（按 Enter 重試 / q 取消）；不強殺
# $Check 是回傳 $true=仍在執行 的 scriptblock，讓 proactive / reactive 共用同一互動流程
function Wait-OpenAverClosed {
    param([scriptblock]$Check)
    while (& $Check) {
        Write-Host ""
        Write-Host "⚠️  OpenAver 目前正在執行，無法覆蓋安裝。" -ForegroundColor Yellow
        Write-Host "   請關閉 OpenAver 視窗後，按 Enter 繼續（或輸入 q 取消）" -ForegroundColor Yellow
        $r = Read-Host
        if ($r -eq 'q' -or $r -eq 'Q') { Write-Host "取消安裝"; exit 0 }
    }
}

# 下載官方 Evergreen bootstrapper 並靜默安裝
# 下載到的 exe 只是 ~2MB bootstrapper，它跑起來才去 Microsoft 抓完整 runtime
# (~150MB) 再裝 —— 慢的是這段，silent 模式不吐可解析的百分比，故只能顯示
# spinner + 已經過秒數，並設 timeout 避免無限等待。
function Install-WebView2 {
    param([int]$TimeoutSec = 300)
    $url = 'https://go.microsoft.com/fwlink/p/?LinkId=2124703'
    $setup = Join-Path $env:TEMP 'MicrosoftEdgeWebview2Setup.exe'
    $prevProgress = $ProgressPreference
    try {
        $ProgressPreference = "SilentlyContinue"
        Invoke-WebRequest -Uri $url -OutFile $setup -UseBasicParsing
        $proc = Start-Process -FilePath $setup -ArgumentList '/silent', '/install' -PassThru
        $spin = '|/-\'; $i = 0; $t0 = Get-Date
        while (-not $proc.HasExited) {
            $el = [int]((Get-Date) - $t0).TotalSeconds
            Write-Host ("`r   下載並安裝中 {0}  {1}s   " -f $spin[$i % 4], $el) -NoNewline
            if ($el -ge $TimeoutSec) { try { $proc.Kill() } catch {}; break }
            Start-Sleep -Milliseconds 250; $i++
        }
        Write-Host ("`r" + (' ' * 40) + "`r") -NoNewline
        return ($proc.HasExited -and $proc.ExitCode -eq 0)
    } catch {
        return $false
    } finally {
        $ProgressPreference = $prevProgress
        Remove-Item $setup -Force -ErrorAction SilentlyContinue
    }
}

# ============ 查詢最新版本 ============
Write-Host "🔍 查詢最新版本..."
try {
    $Release = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest"
} catch {
    Write-Host "❌ 無法連線到 GitHub，請檢查網路" -ForegroundColor Red
    exit 1
}

$Version = $Release.tag_name
$Asset = $Release.assets | Where-Object { $_.name -match "Windows-x64\.zip$" } | Select-Object -First 1

if (-not $Asset) {
    Write-Host "❌ 找不到 Windows 下載連結" -ForegroundColor Red
    exit 1
}

$DownloadUrl = $Asset.browser_download_url
Write-Host "   最新版本: $Version"

# ============ 檢查現有安裝 ============
if (Test-Path $InstallDir) {
    Write-Host ""
    Write-Host "⚠️  已偵測到現有安裝: $InstallDir" -ForegroundColor Yellow
    $Reply = Read-Host "   是否覆蓋安裝？(y/N)"
    if ($Reply -ne "y" -and $Reply -ne "Y") {
        Write-Host "取消安裝"
        exit 0
    }

    # 下載前提早偵測：OpenAver 在跑就先擋，省得白下載 ~80MB 才被卡
    Wait-OpenAverClosed -Check { Test-OpenAverRunning -Dir $InstallDir }
}

# ============ 下載 ============
Write-Host ""
Write-Host "📦 下載 $Version..."
$TmpDir = Join-Path $env:TEMP "OpenAver-install"
$TmpZip = Join-Path $TmpDir "OpenAver.zip"

if (Test-Path $TmpDir) { Remove-Item $TmpDir -Recurse -Force }
New-Item -ItemType Directory -Path $TmpDir -Force | Out-Null

$prevProgress = $ProgressPreference
try {
    $ProgressPreference = "SilentlyContinue"
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $TmpZip -UseBasicParsing
} finally {
    $ProgressPreference = $prevProgress
}

# ============ 清除舊版 embedded Python（避免套件混版）============
# 若 OpenAver 仍在執行，python\pythonw.exe 會被鎖住，Remove-Item 會 throw。
# 鎖才是真正擋我們的東西，所以這裡用 Remove-Item 失敗當權威防線：失敗 →
# 提醒關閉 → 等 Enter 重試（不必重跑整條 irm），不強殺。
$PythonDir = Join-Path $InstallDir "python"
if (Test-Path $PythonDir) {
    Write-Host "🧹 清除舊版 Python runtime..."
    # 權威信號＝Remove-Item 本身能否成功（鎖著就 throw）。失敗 → 提醒 → 等 Enter
    # 重試，user-paced 不會空轉；非 app 因素導致一直失敗時可按 q 退出。
    while ($true) {
        try {
            Remove-Item $PythonDir -Recurse -Force -ErrorAction Stop
            break
        } catch {
            Write-Host ""
            Write-Host "⚠️  無法清除舊版（OpenAver 可能正在執行）。" -ForegroundColor Yellow
            Write-Host "   請關閉 OpenAver 視窗後，按 Enter 重試（或輸入 q 取消）" -ForegroundColor Yellow
            $r = Read-Host
            if ($r -eq 'q' -or $r -eq 'Q') { Write-Host "取消安裝"; exit 0 }
        }
    }
}

# ============ 解壓安裝（覆蓋程式檔案，保留用戶資料）============
Write-Host "📂 安裝到 $InstallDir..."
Expand-ZipRobust -ZipPath $TmpZip -Destination $HOME -ConfineTo $InstallDir

# ============ 解除 Windows 安全限制 ============
Write-Host "🔓 解除 Windows 安全限制..."
Get-ChildItem -Path $InstallDir -Recurse | Unblock-File -ErrorAction SilentlyContinue

# ============ WebView2 Runtime（缺它必開不了）============
if (-not (Test-WebView2)) {
    Write-Host ""
    Write-Host "🌐 偵測到系統未安裝 WebView2 Runtime，正在自動安裝（視網速約 1–3 分鐘）..." -ForegroundColor Yellow
    if ((Install-WebView2) -and (Test-WebView2)) {
        Write-Host "   ✅ WebView2 安裝完成" -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "✅ OpenAver 本體已安裝完成，只差 WebView2。" -ForegroundColor Green
        Write-Host "   WebView2 自動安裝未完成，OpenAver 需要它才能開啟視窗。" -ForegroundColor Yellow
        Write-Host "   請手動安裝：" -ForegroundColor Yellow
        Write-Host "   https://go.microsoft.com/fwlink/p/?LinkId=2124703" -ForegroundColor Cyan
        Write-Host "   裝好後雙擊桌面 OpenAver 捷徑即可啟動。" -ForegroundColor Yellow
    }
}

# ============ 建立桌面捷徑 ============
try {
    $Desktop = [Environment]::GetFolderPath("Desktop")
    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut("$Desktop\OpenAver.lnk")
    $Shortcut.TargetPath = "$InstallDir\OpenAver.bat"
    $Shortcut.WorkingDirectory = $InstallDir
    $Shortcut.Description = "OpenAver"
    $Shortcut.Save()
    Write-Host "🖥️  桌面捷徑已建立"
} catch {
    Write-Host "   (桌面捷徑建立失敗，可手動執行)" -ForegroundColor Yellow
}

# ============ 清理暫存 ============
Remove-Item $TmpDir -Recurse -Force

# ============ 完成 ============
Write-Host ""
Write-Host "✅ 安裝完成！" -ForegroundColor Green
Write-Host ""
Write-Host "   啟動方式："
Write-Host "   1. 雙擊桌面上的 OpenAver 捷徑"
Write-Host "   2. 或執行 $InstallDir\OpenAver.bat"
Write-Host ""
