# OpenAver Windows 安裝程式
$ErrorActionPreference = "Stop"
$Repo = "slive777/OpenAver"
$InstallDir = "$HOME\OpenAver"

Write-Host ""
Write-Host "=============================="
Write-Host "   OpenAver 安裝程式"
Write-Host "=============================="
Write-Host ""

# --- 查詢最新版本 ---
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

# --- 檢查現有安裝 ---
if (Test-Path $InstallDir) {
    Write-Host ""
    Write-Host "⚠️  已偵測到現有安裝: $InstallDir" -ForegroundColor Yellow
    $Reply = Read-Host "   是否覆蓋安裝？(y/N)"
    if ($Reply -ne "y" -and $Reply -ne "Y") {
        Write-Host "取消安裝"
        exit 0
    }
}

# --- 下載 ---
Write-Host ""
Write-Host "📦 下載 $Version..."
$TmpDir = Join-Path $env:TEMP "OpenAver-install"
$TmpZip = Join-Path $TmpDir "OpenAver.zip"

if (Test-Path $TmpDir) { Remove-Item $TmpDir -Recurse -Force }
New-Item -ItemType Directory -Path $TmpDir -Force | Out-Null

$ProgressPreference = "SilentlyContinue"
Invoke-WebRequest -Uri $DownloadUrl -OutFile $TmpZip
$ProgressPreference = "Continue"

# --- 解壓安裝（覆蓋程式檔案，保留用戶資料）---
Write-Host "📂 安裝到 $InstallDir..."
Expand-Archive -Path $TmpZip -DestinationPath $HOME -Force

# --- 解除 Windows 安全限制 ---
Write-Host "🔓 解除 Windows 安全限制..."
Get-ChildItem -Path $InstallDir -Recurse | Unblock-File -ErrorAction SilentlyContinue

# --- 建立桌面捷徑 ---
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

# --- 清理暫存 ---
Remove-Item $TmpDir -Recurse -Force

# --- 完成 ---
Write-Host ""
Write-Host "✅ 安裝完成！" -ForegroundColor Green
Write-Host ""
Write-Host "   啟動方式："
Write-Host "   1. 雙擊桌面上的 OpenAver 捷徑"
Write-Host "   2. 或執行 $InstallDir\OpenAver.bat"
Write-Host ""
