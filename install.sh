#!/bin/bash
set -e

REPO="slive777/OpenAver"
INSTALL_DIR="$HOME/OpenAver"

# ============ 語言判定與訊息表（CD-145b-8b／CD-145b-17）============
detect_installer_lang() {
    # CD-145b-8b：環境變數覆寫優先於系統語言，值不合法就忽略、退回系統判定。
    # 先用 tr 正規化成小寫再比對（bash 3.2 相容，禁用 bash 4 大小寫展開），
    # 讓 EN／Zh-TW 等與 PowerShell -in（大小寫不敏感）行為一致；回傳訊息表用的正規大小寫。
    local _override
    _override=$(printf '%s' "${OPENAVER_INSTALL_LANG:-}" | tr '[:upper:]' '[:lower:]')
    case "$_override" in
        zh-tw) echo "zh-TW"; return ;;
        zh-cn) echo "zh-CN"; return ;;
        ja)    echo "ja"; return ;;
        en)    echo "en"; return ;;
    esac

    local _lc="${LC_ALL:-$LANG}"
    case "$_lc" in
        zh_TW*|zh_HK*|zh_MO*) echo "zh-TW" ;;
        zh_CN*|zh_SG*)        echo "zh-CN" ;;
        ja*)                   echo "ja" ;;
        *)                      echo "en" ;;
    esac
}

LANG_KEY="$(detect_installer_lang)"

t() {
    case "${LANG_KEY}:$1" in
        zh-TW:title_banner) echo "   OpenAver 安裝程式" ;;
        zh-CN:title_banner) echo "   OpenAver 安装程序" ;;
        ja:title_banner) echo "   OpenAver インストーラー" ;;
        en:title_banner) echo "   OpenAver Installer" ;;

        zh-TW:unsupported_os) echo "❌ 此腳本僅支援 macOS 與 Linux" ;;
        zh-CN:unsupported_os) echo "❌ 此脚本仅支持 macOS 与 Linux" ;;
        ja:unsupported_os) echo "❌ このスクリプトは macOS と Linux のみ対応しています" ;;
        en:unsupported_os) echo "❌ This script only supports macOS and Linux" ;;

        zh-TW:install_usage) echo "用法：bash install.sh [--version vX.Y.Z] [--yes]" ;;
        zh-CN:install_usage) echo "用法：bash install.sh [--version vX.Y.Z] [--yes]" ;;
        ja:install_usage) echo "使い方：bash install.sh [--version vX.Y.Z] [--yes]" ;;
        en:install_usage) echo "Usage: bash install.sh [--version vX.Y.Z] [--yes]" ;;

        zh-TW:arch_unsupported_fmt) echo "❌ 不支援的架構：%s" ;;
        zh-CN:arch_unsupported_fmt) echo "❌ 不支持的架构：%s" ;;
        ja:arch_unsupported_fmt) echo "❌ 未対応のアーキテクチャ：%s" ;;
        en:arch_unsupported_fmt) echo "❌ Unsupported architecture: %s" ;;

        zh-TW:libc_musl_unsupported) echo "❌ 不支援 musl（例如 Alpine）；請使用 glibc 發行版" ;;
        zh-CN:libc_musl_unsupported) echo "❌ 不支持 musl（例如 Alpine）；请使用 glibc 发行版" ;;
        ja:libc_musl_unsupported) echo "❌ musl は未対応です（Alpine など）。glibc ディストリビューションを使ってください" ;;
        en:libc_musl_unsupported) echo "❌ musl is not supported (e.g. Alpine); please use a glibc-based distro" ;;

        zh-TW:glibc_too_old_fmt) echo "❌ glibc 版本過舊（偵測到 %s，需要 %s 以上）" ;;
        zh-CN:glibc_too_old_fmt) echo "❌ glibc 版本过旧（检测到 %s，需要 %s 以上）" ;;
        ja:glibc_too_old_fmt) echo "❌ glibc が古すぎます（検出 %s、必要 %s 以上）" ;;
        en:glibc_too_old_fmt) echo "❌ glibc is too old (detected %s, need %s or newer)" ;;

        zh-TW:glibc_unknown) echo "❌ 無法判定 glibc 版本" ;;
        zh-CN:glibc_unknown) echo "❌ 无法判定 glibc 版本" ;;
        ja:glibc_unknown) echo "❌ glibc バージョンを判定できません" ;;
        en:glibc_unknown) echo "❌ Could not determine the glibc version" ;;

        zh-TW:root_reminder) echo "⚠️  目前以 root 執行；建議改用一般使用者帳號" ;;
        zh-CN:root_reminder) echo "⚠️  当前以 root 执行；建议改用普通用户帐号" ;;
        ja:root_reminder) echo "⚠️  root で実行中です。一般ユーザーでの実行を推奨します" ;;
        en:root_reminder) echo "⚠️  Running as root; a normal user account is recommended" ;;

        zh-TW:no_linux_asset_fmt) echo "❌ 這個版本（%s）沒有 Linux 版" ;;
        zh-CN:no_linux_asset_fmt) echo "❌ 这个版本（%s）没有 Linux 版" ;;
        ja:no_linux_asset_fmt) echo "❌ このバージョン（%s）には Linux 版がありません" ;;
        en:no_linux_asset_fmt) echo "❌ This version (%s) has no Linux build" ;;

        zh-TW:tarball_not_found_fmt) echo "❌ 找不到壓縮檔：%s" ;;
        zh-CN:tarball_not_found_fmt) echo "❌ 找不到压缩包：%s" ;;
        ja:tarball_not_found_fmt) echo "❌ アーカイブが見つかりません：%s" ;;
        en:tarball_not_found_fmt) echo "❌ Tarball not found: %s" ;;

        zh-TW:existing_install_refused_fmt) echo "❌ 偵測到 %s 已有安裝，這一版安裝程式目前只處理全新安裝、沒有動任何檔案" ;;
        zh-CN:existing_install_refused_fmt) echo "❌ 检测到 %s 已有安装，这一版安装程序目前只处理全新安装、没有改动任何文件" ;;
        ja:existing_install_refused_fmt) echo "❌ %s に既存インストールを検出したため、この版は新規のみ対応で、ファイルは一切触っていません" ;;
        en:existing_install_refused_fmt) echo "❌ Existing install detected at %s; this installer version only handles fresh installs and left all files untouched" ;;

        zh-TW:download_failed) echo "❌ 下載失敗" ;;
        zh-CN:download_failed) echo "❌ 下载失败" ;;
        ja:download_failed) echo "❌ ダウンロードに失敗しました" ;;
        en:download_failed) echo "❌ Download failed" ;;

        zh-TW:archive_invalid) echo "❌ 壓縮檔內容無效" ;;
        zh-CN:archive_invalid) echo "❌ 压缩包内容无效" ;;
        ja:archive_invalid) echo "❌ アーカイブの内容が無効です" ;;
        en:archive_invalid) echo "❌ Archive contents are invalid" ;;

        zh-TW:verify_failed) echo "❌ 安裝包自檢失敗" ;;
        zh-CN:verify_failed) echo "❌ 安装包自检失败" ;;
        ja:verify_failed) echo "❌ パッケージの自己検査に失敗しました" ;;
        en:verify_failed) echo "❌ Package self-check failed" ;;

        zh-TW:place_failed_fmt) echo "❌ 無法就位：%s" ;;
        zh-CN:place_failed_fmt) echo "❌ 无法就位：%s" ;;
        ja:place_failed_fmt) echo "❌ 配置に失敗しました：%s" ;;
        en:place_failed_fmt) echo "❌ Failed to place: %s" ;;

        zh-TW:local_bin_exists_fmt) echo "⚠️  ~/.local/bin/openaver 已存在且不是符號連結，略過：%s" ;;
        zh-CN:local_bin_exists_fmt) echo "⚠️  ~/.local/bin/openaver 已存在且不是符号链接，跳过：%s" ;;
        ja:local_bin_exists_fmt) echo "⚠️  ~/.local/bin/openaver が既にありシンボリックリンクではないためスキップ：%s" ;;
        en:local_bin_exists_fmt) echo "⚠️  ~/.local/bin/openaver already exists and is not a symlink, skipping: %s" ;;

        zh-TW:local_bin_path_hint) echo "提示：請把 ~/.local/bin 加入 PATH" ;;
        zh-CN:local_bin_path_hint) echo "提示：请把 ~/.local/bin 加入 PATH" ;;
        ja:local_bin_path_hint) echo "ヒント：~/.local/bin を PATH に追加してください" ;;
        en:local_bin_path_hint) echo "Hint: add ~/.local/bin to your PATH" ;;

        zh-TW:ask_autostart) echo "要設定開機自動啟動嗎？(Y/n) " ;;
        zh-CN:ask_autostart) echo "要设置开机自动启动吗？(Y/n) " ;;
        ja:ask_autostart) echo "起動時に自動起動しますか？(Y/n) " ;;
        en:ask_autostart) echo "Enable start on boot? (Y/n) " ;;

        zh-TW:no_tty_default) echo "沒有終端機，預設開啟自動啟動" ;;
        zh-CN:no_tty_default) echo "没有终端机，默认开启自动启动" ;;
        ja:no_tty_default) echo "端末がないため、自動起動を既定で有効にします" ;;
        en:no_tty_default) echo "No terminal available; enabling autostart by default" ;;

        zh-TW:apple_silicon_only) echo "❌ 目前僅支援 Apple Silicon (M1/M2/M3/M4)" ;;
        zh-CN:apple_silicon_only) echo "❌ 目前仅支持 Apple Silicon (M1/M2/M3/M4)" ;;
        ja:apple_silicon_only) echo "❌ 現在は Apple Silicon (M1/M2/M3/M4) のみ対応しています" ;;
        en:apple_silicon_only) echo "❌ Currently only Apple Silicon (M1/M2/M3/M4) is supported" ;;

        zh-TW:detected_arch_fmt) echo "   偵測到架構: %s" ;;
        zh-CN:detected_arch_fmt) echo "   检测到的架构: %s" ;;
        ja:detected_arch_fmt) echo "   検出したアーキテクチャ: %s" ;;
        en:detected_arch_fmt) echo "   Detected architecture: %s" ;;

        zh-TW:app_running_warning) echo "⚠️  OpenAver 目前正在執行，無法覆蓋安裝。" ;;
        zh-CN:app_running_warning) echo "⚠️  OpenAver 当前正在运行，无法覆盖安装。" ;;
        ja:app_running_warning) echo "⚠️  OpenAver が実行中のため、上書きインストールできません。" ;;
        en:app_running_warning) echo "⚠️  OpenAver is currently running, cannot overwrite the installation." ;;

        zh-TW:app_running_close_continue_prompt) echo "   請關閉 OpenAver 後，按 Enter 繼續（或輸入 q 取消）" ;;
        zh-CN:app_running_close_continue_prompt) echo "   请关闭 OpenAver 后，按 Enter 继续（或输入 q 取消）" ;;
        ja:app_running_close_continue_prompt) echo "   OpenAver を終了してから Enter キーを押して続行してください（キャンセルする場合は q を入力）" ;;
        en:app_running_close_continue_prompt) echo "   Please close OpenAver, then press Enter to continue (or type q to cancel)" ;;

        zh-TW:install_cancelled) echo "取消安裝" ;;
        zh-CN:install_cancelled) echo "取消安装" ;;
        ja:install_cancelled) echo "インストールをキャンセルしました" ;;
        en:install_cancelled) echo "Installation cancelled" ;;

        zh-TW:checking_latest_version) echo "🔍 查詢最新版本..." ;;
        zh-CN:checking_latest_version) echo "🔍 正在查询最新版本..." ;;
        ja:checking_latest_version) echo "🔍 最新バージョンを確認中..." ;;
        en:checking_latest_version) echo "🔍 Checking for the latest version..." ;;

        zh-TW:github_connect_failed) echo "❌ 無法連線到 GitHub，請檢查網路" ;;
        zh-CN:github_connect_failed) echo "❌ 无法连接到 GitHub，请检查网络" ;;
        ja:github_connect_failed) echo "❌ GitHub に接続できません。ネットワークを確認してください" ;;
        en:github_connect_failed) echo "❌ Could not connect to GitHub, please check your network connection" ;;

        zh-TW:download_link_not_found) echo "❌ 找不到 macOS 下載連結" ;;
        zh-CN:download_link_not_found) echo "❌ 找不到 macOS 下载链接" ;;
        ja:download_link_not_found) echo "❌ macOS 用のダウンロードリンクが見つかりません" ;;
        en:download_link_not_found) echo "❌ Could not find the macOS download link" ;;

        zh-TW:latest_version_fmt) echo "   最新版本: %s" ;;
        zh-CN:latest_version_fmt) echo "   最新版本: %s" ;;
        ja:latest_version_fmt) echo "   最新バージョン: %s" ;;
        en:latest_version_fmt) echo "   Latest version: %s" ;;

        zh-TW:existing_install_detected_fmt) echo "⚠️  已偵測到現有安裝: %s" ;;
        zh-CN:existing_install_detected_fmt) echo "⚠️  检测到已存在的安装: %s" ;;
        ja:existing_install_detected_fmt) echo "⚠️  既存のインストールを検出しました: %s" ;;
        en:existing_install_detected_fmt) echo "⚠️  Existing installation detected: %s" ;;

        zh-TW:overwrite_confirm_prompt) echo "   是否覆蓋安裝？(y/N) " ;;
        zh-CN:overwrite_confirm_prompt) echo "   是否覆盖安装？(y/N) " ;;
        ja:overwrite_confirm_prompt) echo "   上書きインストールしますか？(y/N) " ;;
        en:overwrite_confirm_prompt) echo "   Overwrite the existing installation? (y/N) " ;;

        zh-TW:downloading_fmt) echo "📦 下載 %s..." ;;
        zh-CN:downloading_fmt) echo "📦 正在下载 %s..." ;;
        ja:downloading_fmt) echo "📦 %s をダウンロード中..." ;;
        en:downloading_fmt) echo "📦 Downloading %s..." ;;

        zh-TW:cleaning_old_python) echo "🧹 清除舊版 Python runtime..." ;;
        zh-CN:cleaning_old_python) echo "🧹 正在清除旧版 Python 运行时..." ;;
        ja:cleaning_old_python) echo "🧹 古いバージョンの Python ランタイムを削除中..." ;;
        en:cleaning_old_python) echo "🧹 Removing old Python runtime..." ;;

        zh-TW:installing_to_fmt) echo "📂 安裝到 %s..." ;;
        zh-CN:installing_to_fmt) echo "📂 正在安装到 %s..." ;;
        ja:installing_to_fmt) echo "📂 %s にインストール中..." ;;
        en:installing_to_fmt) echo "📂 Installing to %s..." ;;

        zh-TW:removing_security_restrictions) echo "🔓 移除 macOS 安全限制..." ;;
        zh-CN:removing_security_restrictions) echo "🔓 正在移除 macOS 安全限制..." ;;
        ja:removing_security_restrictions) echo "🔓 macOS のセキュリティ制限を解除中..." ;;
        en:removing_security_restrictions) echo "🔓 Removing macOS security restrictions..." ;;

        zh-TW:install_complete) echo "✅ 安裝完成！" ;;
        zh-CN:install_complete) echo "✅ 安装完成！" ;;
        ja:install_complete) echo "✅ インストールが完了しました！" ;;
        en:install_complete) echo "✅ Installation complete!" ;;

        zh-TW:launch_instructions_header) echo "   啟動方式：" ;;
        zh-CN:launch_instructions_header) echo "   启动方式：" ;;
        ja:launch_instructions_header) echo "   起動方法：" ;;
        en:launch_instructions_header) echo "   How to launch:" ;;

        zh-TW:launch_instruction_1) echo "   1. 雙擊 ~/OpenAver/OpenAver.command" ;;
        zh-CN:launch_instruction_1) echo "   1. 双击 ~/OpenAver/OpenAver.command" ;;
        ja:launch_instruction_1) echo "   1. ~/OpenAver/OpenAver.command をダブルクリック" ;;
        en:launch_instruction_1) echo "   1. Double-click ~/OpenAver/OpenAver.command" ;;

        zh-TW:launch_instruction_2) echo "   2. 或在 Terminal 執行: ~/OpenAver/OpenAver.command" ;;
        zh-CN:launch_instruction_2) echo "   2. 或在 Terminal 中运行: ~/OpenAver/OpenAver.command" ;;
        ja:launch_instruction_2) echo "   2. または Terminal で実行: ~/OpenAver/OpenAver.command" ;;
        en:launch_instruction_2) echo "   2. Or run it from Terminal: ~/OpenAver/OpenAver.command" ;;

        *) echo "[missing:$1]" ;;
    esac
}

detect_platform() {
    local arch ldd_out ldd_lc ver maj min fmaj fmin raw

    arch="$(uname -m)"
    case "$arch" in
        x86_64|aarch64)
            LINUX_ARCH="$arch"
            ;;
        *)
            printf "$(t arch_unsupported_fmt)\n" "$arch" >&2
            return 1
            ;;
    esac

    ldd_out="$(ldd --version 2>&1)" || true
    ldd_lc="$(printf '%s' "$ldd_out" | tr '[:upper:]' '[:lower:]')"
    case "$ldd_lc" in
        *musl*)
            echo "$(t libc_musl_unsupported)" >&2
            return 1
            ;;
    esac
    for raw in /lib/ld-musl-*; do
        if [ -e "$raw" ] || [ -L "$raw" ]; then
            echo "$(t libc_musl_unsupported)" >&2
            return 1
        fi
        break
    done

    ver="$(getconf GNU_LIBC_VERSION 2>/dev/null)" || {
        echo "$(t glibc_unknown)" >&2
        return 1
    }
    case "$ver" in
        glibc\ *)
            ver="${ver#glibc }"
            ;;
        *)
            echo "$(t glibc_unknown)" >&2
            return 1
            ;;
    esac
    maj="${ver%%.*}"
    min="${ver#*.}"
    min="${min%%.*}"
    case "$maj" in ''|*[!0-9]*) echo "$(t glibc_unknown)" >&2; return 1 ;; esac
    case "$min" in ''|*[!0-9]*) echo "$(t glibc_unknown)" >&2; return 1 ;; esac
    fmaj="${GLIBC_FLOOR%%.*}"
    fmin="${GLIBC_FLOOR#*.}"
    if [ "$maj" -gt "$fmaj" ]; then
        return 0
    fi
    if [ "$maj" -lt "$fmaj" ]; then
        printf "$(t glibc_too_old_fmt)\n" "$ver" "$GLIBC_FLOOR" >&2
        return 1
    fi
    if [ "$min" -ge "$fmin" ]; then
        return 0
    fi
    printf "$(t glibc_too_old_fmt)\n" "$ver" "$GLIBC_FLOOR" >&2
    return 1
}

_linux_cleanup_stage() {
    if [ -z "${STAGE:-}" ]; then
        return 0
    fi
    if [ ! -d "$STAGE" ]; then
        return 0
    fi
    case "$STAGE" in
        "$INSTALL_DIR"/.stage-*)
            rm -rf "$STAGE"
            ;;
    esac
}

GLIBC_FLOOR=2.28
install_linux() {
    set +e
    local ASSUME_YES=0
    local OPT_VERSION=""
    local TARBALL=""
    local DOWNLOAD_URL=""
    local RELEASE_JSON=""
    local VERSION_LABEL=""
    local stage_candidate=""
    local item=""
    local dest=""
    local reply=""
    local do_autostart=1
    local local_bin=""
    # STAGE must be global: EXIT trap runs after this function returns.
    STAGE=""

    if [ "${OPENAVER_YES:-}" = "1" ]; then
        ASSUME_YES=1
    fi
    while [ $# -gt 0 ]; do
        case "$1" in
            --yes)
                ASSUME_YES=1
                shift
                ;;
            --version)
                if [ -z "${2:-}" ]; then
                    echo "$(t install_usage)" >&2
                    return 2
                fi
                OPT_VERSION="$2"
                shift 2
                ;;
            *)
                echo "$(t install_usage)" >&2
                return 2
                ;;
        esac
    done
    if [ -n "$OPT_VERSION" ]; then
        if ! printf '%s\n' "$OPT_VERSION" | grep -Eq '^v[0-9]+\.[0-9]+\.[0-9]+$'; then
            echo "$(t install_usage)" >&2
            return 2
        fi
    fi

    detect_platform || return 1

    if [ "$(id -u)" -eq 0 ]; then
        echo "$(t root_reminder)"
    fi

    if [ -n "${OPENAVER_TARBALL:-}" ]; then
        case "$OPENAVER_TARBALL" in
            http://*|https://*)
                DOWNLOAD_URL="$OPENAVER_TARBALL"
                VERSION_LABEL="$OPENAVER_TARBALL"
                ;;
            *)
                if [ ! -f "$OPENAVER_TARBALL" ]; then
                    printf "$(t tarball_not_found_fmt)\n" "$OPENAVER_TARBALL" >&2
                    return 1
                fi
                TARBALL="$OPENAVER_TARBALL"
                VERSION_LABEL="$OPENAVER_TARBALL"
                ;;
        esac
    elif [ -n "$OPT_VERSION" ]; then
        echo "$(t checking_latest_version)"
        RELEASE_JSON="$(curl -fsSL "https://api.github.com/repos/$REPO/releases/tags/$OPT_VERSION")" || {
            # tags 404 and connect failures both land here via curl -f; prefer asset message for tags.
            printf "$(t no_linux_asset_fmt)\n" "$OPT_VERSION" >&2
            return 1
        }
        VERSION_LABEL="$OPT_VERSION"
        DOWNLOAD_URL="$(printf '%s\n' "$RELEASE_JSON" | grep -o "\"browser_download_url\": *\"[^\"]*Linux-${LINUX_ARCH}\\.tar\\.gz\"" | head -1 | cut -d'"' -f4)"
        if [ -z "$DOWNLOAD_URL" ]; then
            printf "$(t no_linux_asset_fmt)\n" "$OPT_VERSION" >&2
            return 1
        fi
    else
        echo "$(t checking_latest_version)"
        RELEASE_JSON="$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest")" || {
            echo "$(t github_connect_failed)" >&2
            return 1
        }
        VERSION_LABEL="$(printf '%s\n' "$RELEASE_JSON" | grep -o '"tag_name": *"[^"]*"' | head -1 | cut -d'"' -f4)"
        DOWNLOAD_URL="$(printf '%s\n' "$RELEASE_JSON" | grep -o "\"browser_download_url\": *\"[^\"]*Linux-${LINUX_ARCH}\\.tar\\.gz\"" | head -1 | cut -d'"' -f4)"
        if [ -z "$DOWNLOAD_URL" ]; then
            printf "$(t no_linux_asset_fmt)\n" "${VERSION_LABEL:-latest}" >&2
            return 1
        fi
    fi

    for item in app python openaver .prev venv; do
        if [ -e "$INSTALL_DIR/$item" ] || [ -L "$INSTALL_DIR/$item" ]; then
            printf "$(t existing_install_refused_fmt)\n" "$INSTALL_DIR" >&2
            return 1
        fi
    done

    mkdir -p "$INSTALL_DIR" || return 1
    stage_candidate="$INSTALL_DIR/.stage-$(date +%s)-$$"
    mkdir "$stage_candidate" || return 1
    STAGE="$stage_candidate"
    trap '_linux_cleanup_stage' EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM

    if [ -n "$DOWNLOAD_URL" ]; then
        printf "$(t downloading_fmt)\n" "$VERSION_LABEL"
        if ! curl -fSL --progress-bar "$DOWNLOAD_URL" -o "$STAGE/openaver.tar.gz"; then
            echo "$(t download_failed)" >&2
            return 1
        fi
        TARBALL="$STAGE/openaver.tar.gz"
    fi

    printf "$(t installing_to_fmt)\n" "$INSTALL_DIR"
    if ! tar tzf "$TARBALL" >/dev/null; then
        echo "$(t archive_invalid)" >&2
        return 1
    fi
    if ! tar xzf "$TARBALL" -C "$STAGE"; then
        echo "$(t archive_invalid)" >&2
        return 1
    fi
    if [ ! -e "$STAGE/OpenAver/app" ] || [ ! -e "$STAGE/OpenAver/python" ] || \
       { [ ! -e "$STAGE/OpenAver/openaver" ] && [ ! -L "$STAGE/OpenAver/openaver" ]; } || \
       [ ! -f "$STAGE/OpenAver/app/core/version.py" ]; then
        echo "$(t archive_invalid)" >&2
        return 1
    fi

    if ! ( cd "$STAGE/OpenAver" && PYTHONDONTWRITEBYTECODE=1 python/bin/python3 app/scripts/verify_artifact_imports.py ); then
        echo "$(t verify_failed)" >&2
        return 1
    fi

    for item in app python openaver; do
        if ! mv "$STAGE/OpenAver/$item" "$INSTALL_DIR/"; then
            printf "$(t place_failed_fmt)\n" "$item" >&2
            return 1
        fi
    done

    "$INSTALL_DIR/openaver" _prepare || return 1

    local_bin="$HOME/.local/bin"
    dest="$local_bin/openaver"
    if [ -L "$dest" ]; then
        ln -sfn "$INSTALL_DIR/openaver" "$dest" || return 1
    elif [ -e "$dest" ]; then
        printf "$(t local_bin_exists_fmt)\n" "$dest"
    else
        mkdir -p "$local_bin" || return 1
        ln -s "$INSTALL_DIR/openaver" "$dest" || return 1
    fi
    case ":$PATH:" in
        *":$local_bin:"*) ;;
        *) echo "$(t local_bin_path_hint)" ;;
    esac

    echo "$(t install_complete)"

    do_autostart=1
    if { exec 3</dev/tty; } 2>/dev/null; then
        printf "%s" "$(t ask_autostart)"
        IFS= read -r reply <&3 || reply=""
        exec 3<&-
        case "$reply" in
            n|N) do_autostart=0 ;;
        esac
    else
        echo "$(t no_tty_default)"
    fi
    if [ "$do_autostart" -eq 1 ]; then
        "$INSTALL_DIR/openaver" autostart on || return $?
    else
        "$INSTALL_DIR/openaver" autostart off || return $?
    fi

    if [ "${OPENAVER_INSTALL_NO_START:-}" != "1" ]; then
        "$INSTALL_DIR/openaver" start || return $?
        "$INSTALL_DIR/openaver" url || return $?
    fi

    return 0
}

echo ""
echo "=============================="
echo "$(t title_banner)"
echo "=============================="
echo ""

# --- 偵測 OS ---
case "$(uname)" in
    Darwin) ;;
    Linux) install_linux "$@"; exit $? ;;
    *) echo "$(t unsupported_os)" >&2; exit 1 ;;
esac

# --- 偵測架構 ---
ARCH=$(uname -m)
if [[ "$ARCH" != "arm64" ]]; then
    echo "$(t apple_silicon_only)"
    printf "$(t detected_arch_fmt)\n" "$ARCH"
    exit 1
fi

# --- OpenAver 執行中偵測 ---
# macOS rm 對 advisory lock 不會 fail，故 rm 成敗不是權威信號，pgrep 才是。
is_openaver_running() {
    # 權威信號：app 一律以 python3 -c "...from windows.standalone import main..." 啟動。
    # 不能靠 OpenAver.command（wrapper 用 nohup & 後即 exit、不在 process list），
    # 也不能靠絕對路徑 python（argv[0] 是相對的 ./python/bin/python3 → false negative）。
    # 改抓 -c 內這串 OpenAver 獨有、與安裝位置無關的字串。
    pgrep -f "from windows.standalone import main" > /dev/null 2>&1 || \
    pgrep -f "$INSTALL_DIR/python/bin" > /dev/null 2>&1
}

# 提醒關閉並等待（Enter 重試 / q 取消），不強殺；不必重跑整條指令
wait_openaver_closed() {
    while is_openaver_running; do
        echo ""
        echo "$(t app_running_warning)"
        echo "$(t app_running_close_continue_prompt)"
        local REPLY
        read -r REPLY < /dev/tty
        if [[ "$REPLY" == "q" || "$REPLY" == "Q" ]]; then
            echo "$(t install_cancelled)"
            exit 0
        fi
    done
}

# --- 查詢最新版本 ---
echo "$(t checking_latest_version)"
RELEASE_JSON=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest") || {
    echo "$(t github_connect_failed)"
    exit 1
}

VERSION=$(echo "$RELEASE_JSON" | grep -o '"tag_name": *"[^"]*"' | head -1 | cut -d'"' -f4)
DOWNLOAD_URL=$(echo "$RELEASE_JSON" | grep -o '"browser_download_url": *"[^"]*macOS-arm64[^"]*\.zip"' | head -1 | cut -d'"' -f4)

if [[ -z "$DOWNLOAD_URL" ]]; then
    echo "$(t download_link_not_found)"
    exit 1
fi

printf "$(t latest_version_fmt)\n" "$VERSION"

# --- 檢查現有安裝 ---
if [[ -d "$INSTALL_DIR" ]]; then
    echo ""
    printf "$(t existing_install_detected_fmt)\n" "$INSTALL_DIR"
    read -p "$(t overwrite_confirm_prompt)" -n 1 -r REPLY < /dev/tty
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "$(t install_cancelled)"
        exit 0
    fi

    # 下載前提早偵測：OpenAver 在跑就先擋，省得白下載才被卡
    wait_openaver_closed
fi

# --- 下載 ---
echo ""
printf "$(t downloading_fmt)\n" "$VERSION"
TMP_DIR=$(mktemp -d)
TMP_ZIP="$TMP_DIR/OpenAver.zip"
curl -fSL --progress-bar "$DOWNLOAD_URL" -o "$TMP_ZIP"

# --- 清除舊版 embedded Python（避免套件混版）---
# macOS rm 對 advisory lock 不會 fail，必須事前用 pgrep 攔截，否則會悄悄混版。
# 權威信號＝pgrep；仍在跑就提醒關閉並等待（不重跑指令、不強殺）後再 rm。
if [[ -d "$INSTALL_DIR/python" ]]; then
    wait_openaver_closed
    echo "$(t cleaning_old_python)"
    rm -rf "$INSTALL_DIR/python"
fi

# --- 解壓安裝（覆蓋程式檔案，保留用戶資料）---
printf "$(t installing_to_fmt)\n" "$INSTALL_DIR"
unzip -o -q "$TMP_ZIP" -d "$HOME"

# --- 移除 macOS 安全限制 ---
echo "$(t removing_security_restrictions)"
xattr -dr com.apple.quarantine "$INSTALL_DIR" 2>/dev/null || true
chmod +x "$INSTALL_DIR/OpenAver.command"

# --- 清理暫存 ---
rm -rf "$TMP_DIR"

# --- 完成 ---
echo ""
echo "$(t install_complete)"
echo ""
echo "$(t launch_instructions_header)"
echo "$(t launch_instruction_1)"
echo "$(t launch_instruction_2)"
echo ""
