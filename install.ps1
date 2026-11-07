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

function Exit-WithPause {
    param([int]$Code = 0)
    Write-Host ""
    Write-Host $(if ($T) { $T.exit_prompt } else { "Press Enter to close this window" })
    try { $Host.UI.RawUI.FlushInputBuffer() } catch {}
    Read-Host | Out-Null
    exit $Code
}

# 位置約束補寫（CD-120d-10）：真正的硬約束是 Exit-WithPause 函式必須在任何
# 可能出錯的程式碼之前定義——實測把函式定義移到錯誤點之後，trap 有觸發
# 但死在 CommandNotFoundException，而且沒有停住。至於 trap 本身，PowerShell
# 在 scope 內會提升它，寫在檔案最後一行仍然接得到前面的錯誤（所以「trap
# 必須擺在所有工作之前」這個常見說法是錯的）。現行「函式定義 → trap →
# 工作」的順序同時滿足兩者，且仍是最省事的表達方式，故守衛的位置斷言維持不變。
trap {
    Write-Host ""
    Write-Host $(if ($T) { $T.trap_error_header } else { "An unexpected error occurred during installation" }) -ForegroundColor Red
    Write-Host "$_" -ForegroundColor Red
    try {
        if ($_.InvocationInfo) {
            Write-Host "$($_.InvocationInfo.PositionMessage)" -ForegroundColor Red
        }
    } catch {}
    Exit-WithPause 1
}

# ============ 關閉 QuickEdit（CD-145b-9）============
# QuickEdit 模式下，滑鼠在主控台視窗裡點一下會讓下一次 Write-Host 卡住，
# 直到按 Enter/Esc 才放行——這正是 F1 要修的「安裝視窗停在半路等人按 Enter」。
# 只清這一個視窗自己的 console mode，不寫登錄檔，關掉視窗即失效（CD-145b-1）。
# 失敗必須吞掉，不能讓 trap 觸發——非互動情境（無真實 console handle）下
# GetConsoleMode 會回 False，安靜跳過，這是已知且允許的降級，不是 bug。
try {
    $sig = @'
using System;
using System.Runtime.InteropServices;
public static class OpenAverConsole {
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern IntPtr GetStdHandle(int nStdHandle);
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool GetConsoleMode(IntPtr hConsoleHandle, out uint lpMode);
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool SetConsoleMode(IntPtr hConsoleHandle, uint dwMode);
}
'@
    Add-Type -TypeDefinition $sig -ErrorAction Stop
    $STD_INPUT_HANDLE = -10
    $ENABLE_QUICK_EDIT_MODE = 0x0040
    $ENABLE_EXTENDED_FLAGS = 0x0080
    $hStdIn = [OpenAverConsole]::GetStdHandle($STD_INPUT_HANDLE)
    [uint32]$mode = 0
    if ([OpenAverConsole]::GetConsoleMode($hStdIn, [ref]$mode)) {
        # 兩個 flag 必須一起設：只清 QUICK_EDIT 不加 EXTENDED_FLAGS 不會生效
        # （Win32 文件：SetConsoleMode 要求 ENABLE_EXTENDED_FLAGS 開著，
        #  ENABLE_INSERT_MODE/ENABLE_QUICK_EDIT_MODE 的寫入才會被採用）。
        $newMode = ($mode -band (-bnot $ENABLE_QUICK_EDIT_MODE)) -bor $ENABLE_EXTENDED_FLAGS
        [OpenAverConsole]::SetConsoleMode($hStdIn, $newMode) | Out-Null
    }
} catch {}

# ============ 語言判定與訊息表（CD-145b-8b／CD-145b-10）============
function Get-InstallerLang {
    # CD-145b-8b：環境變數覆寫優先於系統顯示語言，值不合法就忽略、退回系統判定。
    $o = $env:OPENAVER_INSTALL_LANG
    if ($o -in 'zh-TW', 'zh-CN', 'ja', 'en') { return $o }

    $name = (Get-UICulture).Name
    if ($name -match '^zh-(TW|HK|MO|Hant)') { return 'zh-TW' }
    if ($name -match '^zh-(CN|SG|Hans)') { return 'zh-CN' }
    if ($name -match '^ja') { return 'ja' }
    return 'en'
}

$L = @{
    'zh-TW' = @{
        exit_prompt = "請按 Enter 關閉此視窗"
        trap_error_header = "❌ 安裝過程發生未預期錯誤"
        title_banner = "   OpenAver 安裝程式"
        app_running_warning = "⚠️  OpenAver 目前正在執行，無法覆蓋安裝。"
        app_running_close_continue_prompt = "   請關閉 OpenAver 視窗後，按 Enter 繼續（或輸入 q 取消）"
        install_cancelled = "取消安裝"
        webview2_progress_fmt = "`r   下載並安裝中 {0}  {1}s   "
        checking_latest_version = "🔍 查詢最新版本..."
        github_connect_failed = "❌ 無法連線到 GitHub，請檢查網路"
        download_link_not_found = "❌ 找不到 Windows 下載連結"
        latest_version_fmt = "   最新版本: {0}"
        existing_install_detected_fmt = "⚠️  已偵測到現有安裝: {0}"
        overwrite_confirm_prompt = "   是否覆蓋安裝？(y/N)"
        downloading_fmt = "📦 下載 {0}..."
        cleaning_old_python = "🧹 清除舊版 Python runtime..."
        cleanup_failed_warning = "⚠️  無法清除舊版（OpenAver 可能正在執行）。"
        cleanup_failed_close_retry_prompt = "   請關閉 OpenAver 視窗後，按 Enter 重試（或輸入 q 取消）"
        installing_to_fmt = "📂 安裝到 {0}..."
        removing_security_restrictions = "🔓 解除 Windows 安全限制..."
        webview2_installing = "🌐 偵測到系統未安裝 WebView2 Runtime，正在自動安裝（視網速約 1–3 分鐘）..."
        webview2_install_success = "   ✅ WebView2 安裝完成"
        webview2_install_incomplete_header = "✅ OpenAver 本體已安裝完成，只差 WebView2。"
        webview2_manual_required = "   WebView2 自動安裝未完成，OpenAver 需要它才能開啟視窗。"
        webview2_manual_instruction = "   請手動安裝："
        webview2_after_install_instruction = "   裝好後雙擊桌面 OpenAver 捷徑即可啟動。"
        desktop_shortcut_created = "🖥️  桌面捷徑已建立"
        desktop_shortcut_failed = "   (桌面捷徑建立失敗，可手動執行)"
        install_complete = "✅ 安裝完成！"
        launch_instructions_header = "   啟動方式："
        launch_instruction_1 = "   1. 雙擊桌面上的 OpenAver 捷徑"
        launch_instruction_2_fmt = "   2. 或執行 {0}\OpenAver.bat"
    }
    'zh-CN' = @{
        exit_prompt = "请按 Enter 关闭此窗口"
        trap_error_header = "❌ 安装过程中发生意外错误"
        title_banner = "   OpenAver 安装程序"
        app_running_warning = "⚠️  OpenAver 当前正在运行，无法覆盖安装。"
        app_running_close_continue_prompt = "   请关闭 OpenAver 窗口后，按 Enter 继续（或输入 q 取消）"
        install_cancelled = "取消安装"
        webview2_progress_fmt = "`r   正在下载安装 {0}  {1}s   "
        checking_latest_version = "🔍 正在查询最新版本..."
        github_connect_failed = "❌ 无法连接到 GitHub，请检查网络"
        download_link_not_found = "❌ 找不到 Windows 下载链接"
        latest_version_fmt = "   最新版本: {0}"
        existing_install_detected_fmt = "⚠️  检测到已存在的安装: {0}"
        overwrite_confirm_prompt = "   是否覆盖安装？(y/N)"
        downloading_fmt = "📦 正在下载 {0}..."
        cleaning_old_python = "🧹 正在清除旧版 Python 运行时..."
        cleanup_failed_warning = "⚠️  无法清除旧版（OpenAver 可能正在运行）。"
        cleanup_failed_close_retry_prompt = "   请关闭 OpenAver 窗口后，按 Enter 重试（或输入 q 取消）"
        installing_to_fmt = "📂 正在安装到 {0}..."
        removing_security_restrictions = "🔓 正在解除 Windows 安全限制..."
        webview2_installing = "🌐 检测到系统未安装 WebView2 Runtime，正在自动安装（视网速约 1–3 分钟）..."
        webview2_install_success = "   ✅ WebView2 安装完成"
        webview2_install_incomplete_header = "✅ OpenAver 本体已安装完成，只差 WebView2。"
        webview2_manual_required = "   WebView2 自动安装未完成，OpenAver 需要它才能打开窗口。"
        webview2_manual_instruction = "   请手动安装："
        webview2_after_install_instruction = "   安装完成后，双击桌面上的 OpenAver 快捷方式即可启动。"
        desktop_shortcut_created = "🖥️  桌面快捷方式已创建"
        desktop_shortcut_failed = "   (桌面快捷方式创建失败，可手动运行)"
        install_complete = "✅ 安装完成！"
        launch_instructions_header = "   启动方式："
        launch_instruction_1 = "   1. 双击桌面上的 OpenAver 快捷方式"
        launch_instruction_2_fmt = "   2. 或运行 {0}\OpenAver.bat"
    }
    'ja' = @{
        exit_prompt = "Enter キーを押してこのウィンドウを閉じてください"
        trap_error_header = "❌ インストール中に予期しないエラーが発生しました"
        title_banner = "   OpenAver インストーラー"
        app_running_warning = "⚠️  OpenAver が実行中のため、上書きインストールできません。"
        app_running_close_continue_prompt = "   OpenAver のウィンドウを閉じてから Enter キーを押して続行してください（キャンセルする場合は q を入力）"
        install_cancelled = "インストールをキャンセルしました"
        webview2_progress_fmt = "`r   ダウンロードとインストール中 {0}  {1}秒   "
        checking_latest_version = "🔍 最新バージョンを確認中..."
        github_connect_failed = "❌ GitHub に接続できません。ネットワークを確認してください"
        download_link_not_found = "❌ Windows 用のダウンロードリンクが見つかりません"
        latest_version_fmt = "   最新バージョン: {0}"
        existing_install_detected_fmt = "⚠️  既存のインストールを検出しました: {0}"
        overwrite_confirm_prompt = "   上書きインストールしますか？(y/N)"
        downloading_fmt = "📦 {0} をダウンロード中..."
        cleaning_old_python = "🧹 古いバージョンの Python ランタイムを削除中..."
        cleanup_failed_warning = "⚠️  旧バージョンを削除できません（OpenAver が実行中の可能性があります）。"
        cleanup_failed_close_retry_prompt = "   OpenAver のウィンドウを閉じてから Enter キーを押して再試行してください（キャンセルする場合は q を入力）"
        installing_to_fmt = "📂 {0} にインストール中..."
        removing_security_restrictions = "🔓 Windows のセキュリティ制限を解除中..."
        webview2_installing = "🌐 WebView2 Runtime が未インストールのため、自動的にインストールしています（回線速度により約 1～3 分かかります）..."
        webview2_install_success = "   ✅ WebView2 のインストールが完了しました"
        webview2_install_incomplete_header = "✅ OpenAver 本体のインストールは完了しました。あとは WebView2 だけです。"
        webview2_manual_required = "   WebView2 の自動インストールが完了しませんでした。OpenAver の起動には WebView2 が必要です。"
        webview2_manual_instruction = "   手動でインストールしてください："
        webview2_after_install_instruction = "   インストール後、デスクトップの OpenAver ショートカットをダブルクリックすると起動できます。"
        desktop_shortcut_created = "🖥️  デスクトップショートカットを作成しました"
        desktop_shortcut_failed = "   (デスクトップショートカットの作成に失敗しました。手動で実行してください)"
        install_complete = "✅ インストールが完了しました！"
        launch_instructions_header = "   起動方法："
        launch_instruction_1 = "   1. デスクトップの OpenAver ショートカットをダブルクリック"
        launch_instruction_2_fmt = "   2. または {0}\OpenAver.bat を実行"
    }
    'en' = @{
        exit_prompt = "Press Enter to close this window"
        trap_error_header = "An unexpected error occurred during installation"
        title_banner = "   OpenAver Installer"
        app_running_warning = "⚠️  OpenAver is currently running, cannot overwrite the installation."
        app_running_close_continue_prompt = "   Please close OpenAver, then press Enter to continue (or type q to cancel)"
        install_cancelled = "Installation cancelled"
        webview2_progress_fmt = "`r   Downloading and installing {0}  {1}s   "
        checking_latest_version = "🔍 Checking for the latest version..."
        github_connect_failed = "❌ Could not connect to GitHub, please check your network connection"
        download_link_not_found = "❌ Could not find the Windows download link"
        latest_version_fmt = "   Latest version: {0}"
        existing_install_detected_fmt = "⚠️  Existing installation detected: {0}"
        overwrite_confirm_prompt = "   Overwrite the existing installation? (y/N)"
        downloading_fmt = "📦 Downloading {0}..."
        cleaning_old_python = "🧹 Removing old Python runtime..."
        cleanup_failed_warning = "⚠️  Could not remove the old version (OpenAver may still be running)."
        cleanup_failed_close_retry_prompt = "   Please close OpenAver, then press Enter to retry (or type q to cancel)"
        installing_to_fmt = "📂 Installing to {0}..."
        removing_security_restrictions = "🔓 Removing Windows security restrictions..."
        webview2_installing = "🌐 WebView2 Runtime not detected, installing it automatically (this may take 1-3 minutes depending on your connection speed)..."
        webview2_install_success = "   ✅ WebView2 installed successfully"
        webview2_install_incomplete_header = "✅ OpenAver itself has been installed, only WebView2 is missing."
        webview2_manual_required = "   WebView2 automatic installation did not complete. OpenAver needs it to open its window."
        webview2_manual_instruction = "   Please install it manually:"
        webview2_after_install_instruction = "   After installing it, double-click the OpenAver shortcut on your desktop to launch it."
        desktop_shortcut_created = "🖥️  Desktop shortcut created"
        desktop_shortcut_failed = "   (Failed to create the desktop shortcut, you can launch it manually)"
        install_complete = "✅ Installation complete!"
        launch_instructions_header = "   How to launch:"
        launch_instruction_1 = "   1. Double-click the OpenAver shortcut on your desktop"
        launch_instruction_2_fmt = "   2. Or run {0}\OpenAver.bat"
    }
}
$Lang = Get-InstallerLang
$T = $L[$Lang]

# 乾淨映像 / 舊系統的 PowerShell 5.1 預設可能用 TLS1.0，GitHub 會拒連
try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}

Write-Host ""
Write-Host "=============================="
Write-Host $T.title_banner
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
        Write-Host $T.app_running_warning -ForegroundColor Yellow
        Write-Host $T.app_running_close_continue_prompt -ForegroundColor Yellow
        $r = Read-Host
        if ($r -eq 'q' -or $r -eq 'Q') { Write-Host $T.install_cancelled; Exit-WithPause 0 }
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
            Write-Host ($T.webview2_progress_fmt -f $spin[$i % 4], $el) -NoNewline
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
Write-Host $T.checking_latest_version
try {
    $Release = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest"
} catch {
    Write-Host $T.github_connect_failed -ForegroundColor Red
    Exit-WithPause 1
}

$Version = $Release.tag_name
$Asset = $Release.assets | Where-Object { $_.name -match "Windows-x64\.zip$" } | Select-Object -First 1

if (-not $Asset) {
    Write-Host $T.download_link_not_found -ForegroundColor Red
    Exit-WithPause 1
}

$DownloadUrl = $Asset.browser_download_url
Write-Host ($T.latest_version_fmt -f $Version)

# ============ 檢查現有安裝 ============
if (Test-Path $InstallDir) {
    Write-Host ""
    Write-Host ($T.existing_install_detected_fmt -f $InstallDir) -ForegroundColor Yellow
    $Reply = Read-Host $T.overwrite_confirm_prompt
    if ($Reply -ne "y" -and $Reply -ne "Y") {
        Write-Host $T.install_cancelled
        Exit-WithPause 0
    }

    # 下載前提早偵測：OpenAver 在跑就先擋，省得白下載 ~80MB 才被卡
    Wait-OpenAverClosed -Check { Test-OpenAverRunning -Dir $InstallDir }
}

# ============ 下載 ============
Write-Host ""
Write-Host ($T.downloading_fmt -f $Version)
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
    Write-Host $T.cleaning_old_python
    # 權威信號＝Remove-Item 本身能否成功（鎖著就 throw）。失敗 → 提醒 → 等 Enter
    # 重試，user-paced 不會空轉；非 app 因素導致一直失敗時可按 q 退出。
    while ($true) {
        try {
            Remove-Item $PythonDir -Recurse -Force -ErrorAction Stop
            break
        } catch {
            Write-Host ""
            Write-Host $T.cleanup_failed_warning -ForegroundColor Yellow
            Write-Host $T.cleanup_failed_close_retry_prompt -ForegroundColor Yellow
            $r = Read-Host
            if ($r -eq 'q' -or $r -eq 'Q') { Write-Host $T.install_cancelled; Exit-WithPause 0 }
        }
    }
}

# ============ 解壓安裝（覆蓋程式檔案，保留用戶資料）============
Write-Host ($T.installing_to_fmt -f $InstallDir)
Expand-ZipRobust -ZipPath $TmpZip -Destination $HOME -ConfineTo $InstallDir

# ============ 解除 Windows 安全限制 ============
Write-Host $T.removing_security_restrictions
Get-ChildItem -Path $InstallDir -Recurse | Unblock-File -ErrorAction SilentlyContinue

# ============ WebView2 Runtime（缺它必開不了）============
if (-not (Test-WebView2)) {
    Write-Host ""
    Write-Host $T.webview2_installing -ForegroundColor Yellow
    if ((Install-WebView2) -and (Test-WebView2)) {
        Write-Host $T.webview2_install_success -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host $T.webview2_install_incomplete_header -ForegroundColor Green
        Write-Host $T.webview2_manual_required -ForegroundColor Yellow
        Write-Host $T.webview2_manual_instruction -ForegroundColor Yellow
        Write-Host "   https://go.microsoft.com/fwlink/p/?LinkId=2124703" -ForegroundColor Cyan
        Write-Host $T.webview2_after_install_instruction -ForegroundColor Yellow
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
    $Shortcut.IconLocation = "$InstallDir\app\web\static\openaver.ico,0"
    $Shortcut.Save()
    Write-Host $T.desktop_shortcut_created
} catch {
    Write-Host $T.desktop_shortcut_failed -ForegroundColor Yellow
}

# ============ 清理暫存 ============
Remove-Item $TmpDir -Recurse -Force

# ============ 完成 ============
Write-Host ""
Write-Host $T.install_complete -ForegroundColor Green
Write-Host ""
Write-Host $T.launch_instructions_header
Write-Host $T.launch_instruction_1
Write-Host ($T.launch_instruction_2_fmt -f $InstallDir)
Write-Host ""
Exit-WithPause 0
