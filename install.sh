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

        zh-TW:install_usage) echo "用法：bash install.sh [--version vX.Y.Z] [--yes] [--update]" ;;
        zh-CN:install_usage) echo "用法：bash install.sh [--version vX.Y.Z] [--yes] [--update]" ;;
        ja:install_usage) echo "使い方：bash install.sh [--version vX.Y.Z] [--yes] [--update]" ;;
        en:install_usage) echo "Usage: bash install.sh [--version vX.Y.Z] [--yes] [--update]" ;;

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

        zh-TW:root_reminder) echo "⚠️  目前以 root 執行；之後寫出的 NFO、封面，你自己的帳號可能改不動，建議改用一般使用者帳號" ;;
        zh-CN:root_reminder) echo "⚠️  当前以 root 执行；之后写出的 NFO、封面，你自己的帐号可能改不动，建议改用普通用户帐号" ;;
        ja:root_reminder) echo "⚠️  root で実行中です。今後書き出される NFO やカバー画像を、ご自身のアカウントでは変更できなくなる場合があります。一般ユーザーでの実行を推奨します" ;;
        en:root_reminder) echo "⚠️  Running as root; NFO files and covers written later may not be editable by your own account. A normal user account is recommended" ;;

        zh-TW:no_linux_asset_fmt) echo "❌ 這個版本（%s）沒有 Linux 版" ;;
        zh-CN:no_linux_asset_fmt) echo "❌ 这个版本（%s）没有 Linux 版" ;;
        ja:no_linux_asset_fmt) echo "❌ このバージョン（%s）には Linux 版がありません" ;;
        en:no_linux_asset_fmt) echo "❌ This version (%s) has no Linux build" ;;

        zh-TW:tarball_not_found_fmt) echo "❌ 找不到壓縮檔：%s" ;;
        zh-CN:tarball_not_found_fmt) echo "❌ 找不到压缩包：%s" ;;
        ja:tarball_not_found_fmt) echo "❌ アーカイブが見つかりません：%s" ;;
        en:tarball_not_found_fmt) echo "❌ Tarball not found: %s" ;;

        zh-TW:update_not_installed) echo "❌ 這台機器還沒有安裝 OpenAver，沒有動任何檔案。請直接執行安裝指令" ;;
        zh-CN:update_not_installed) echo "❌ 这台机器还没有安装 OpenAver，没有改动任何文件。请直接运行安装命令" ;;
        ja:update_not_installed) echo "❌ このマシンには OpenAver がインストールされていません。ファイルは一切触っていません。インストールコマンドを直接実行してください" ;;
        en:update_not_installed) echo "❌ OpenAver is not installed on this machine; no files were touched. Run the install command instead" ;;

        zh-TW:already_latest_fmt) echo "已是最新版本（%s），沒有需要更新的" ;;
        zh-CN:already_latest_fmt) echo "已是最新版本（%s），没有需要更新的" ;;
        ja:already_latest_fmt) echo "すでに最新バージョン（%s）です。更新するものはありません" ;;
        en:already_latest_fmt) echo "Already up to date (%s); nothing to update" ;;

        zh-TW:update_stop_failed) echo "❌ 無法停止目前執行中的 OpenAver，升級沒有進行，也沒有動任何檔案" ;;
        zh-CN:update_stop_failed) echo "❌ 无法停止当前运行的 OpenAver，升级没有进行，也没有改动任何文件" ;;
        ja:update_stop_failed) echo "❌ 実行中の OpenAver を停止できませんでした。アップグレードは行われず、ファイルも変更していません" ;;
        en:update_stop_failed) echo "❌ Could not stop the running OpenAver; the upgrade did not proceed and no files were changed" ;;

        zh-TW:upgrade_rolled_back) echo "❌ 這次沒有完成，已還原成這次之前的版本與服務狀態。原因請看上面的訊息，或 ~/OpenAver/logs/server.log" ;;
        zh-CN:upgrade_rolled_back) echo "❌ 这次没有完成，已还原成这次之前的版本与服务状态。原因请看上面的信息，或 ~/OpenAver/logs/server.log" ;;
        ja:upgrade_rolled_back) echo "❌ 今回は完了せず、以前のバージョンとサービス状態に戻しました。原因は上のメッセージか ~/OpenAver/logs/server.log を確認してください" ;;
        en:upgrade_rolled_back) echo "❌ This run did not finish; the previous version and service state were restored. See the messages above or ~/OpenAver/logs/server.log for the cause" ;;

        zh-TW:rollback_incomplete_fmt) echo "❌ 還原沒有完全成功。請檢查 %s，舊版的檔案可能還在其中的 .prev 資料夾裡，請先不要刪除，處理好之後再重新執行安裝指令" ;;
        zh-CN:rollback_incomplete_fmt) echo "❌ 还原没有完全成功。请检查 %s，旧版的文件可能还在其中的 .prev 文件夹里，请先不要删除，处理好之后再重新运行安装命令" ;;
        ja:rollback_incomplete_fmt) echo "❌ 元に戻す処理が完全には成功しませんでした。%s を確認してください。古いバージョンのファイルがその中の .prev フォルダーに残っている可能性があります。削除せず、対処してからインストールコマンドを再実行してください" ;;
        en:rollback_incomplete_fmt) echo "❌ The restore did not fully succeed. Check %s: the old version's files may still be in its .prev folder - do not delete it, fix things up, then rerun the install command" ;;

        zh-TW:leftover_notice_fmt) echo "提示：~/OpenAver/ 裡有上次升級的殘留（%s），安裝程式不會動它們，確認沒問題可自行刪除" ;;
        zh-CN:leftover_notice_fmt) echo "提示：~/OpenAver/ 里有上次升级的残留（%s），安装程序不会动它们，确认没问题可自行删除" ;;
        ja:leftover_notice_fmt) echo "ヒント：~/OpenAver/ に前回のアップグレードの残骸があります（%s）。インストーラーは触りません。問題がなければご自身で削除してください" ;;
        en:leftover_notice_fmt) echo "Note: ~/OpenAver/ holds leftovers from a previous upgrade (%s). The installer leaves them alone - delete them yourself once you have confirmed everything works" ;;

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

        zh-TW:retrofit_notice_fmt) echo "偵測到舊的手動安裝。output/ 保留（片庫與設定不會丟）；venv/ 與其他舊程式檔會搬到 ~/OpenAver/%s/，你自己放的檔不動；之後改用內附的 Python 執行。" ;;
        zh-CN:retrofit_notice_fmt) echo "检测到旧的手动安装。output/ 保留（片库与设置不会丢）；venv/ 与其他旧程序文件会搬到 ~/OpenAver/%s/，你自己放的文件不动；之后改用内附的 Python 运行。" ;;
        ja:retrofit_notice_fmt) echo "古い手動インストールを検出しました。output/ は保持されます（ライブラリと設定は失われません）。venv/ とその他の古いプログラムファイルは ~/OpenAver/%s/ へ移動します。ご自身で置いたファイルには触りません。今後は同梱の Python で動作します。" ;;
        en:retrofit_notice_fmt) echo "An old manual install was detected. output/ is kept (your library and settings are not lost); venv/ and other old program files will be moved to ~/OpenAver/%s/ and files you put there yourself are left alone. It will then run on the bundled Python." ;;

        zh-TW:retrofit_confirm_prompt) echo "要繼續改裝嗎？(y/N) " ;;
        zh-CN:retrofit_confirm_prompt) echo "要继续改装吗？(y/N) " ;;
        ja:retrofit_confirm_prompt) echo "続行して切り替えますか？(y/N) " ;;
        en:retrofit_confirm_prompt) echo "Continue with the switch? (y/N) " ;;

        zh-TW:retrofit_needs_yes) echo "❌ 偵測到舊的手動安裝，需要你確認才能改裝，但目前沒有終端機可以詢問，沒有動任何檔案。要同意的話，請加上環境變數 OPENAVER_YES=1（或參數 --yes）重新執行" ;;
        zh-CN:retrofit_needs_yes) echo "❌ 检测到旧的手动安装，需要你确认才能改装，但当前没有终端可以询问，没有改动任何文件。如同意，请加上环境变量 OPENAVER_YES=1（或参数 --yes）重新运行" ;;
        ja:retrofit_needs_yes) echo "❌ 古い手動インストールを検出しました。切り替えには確認が必要ですが、端末がなく確認できないため、ファイルは一切触っていません。同意する場合は環境変数 OPENAVER_YES=1（または --yes）を付けて再実行してください" ;;
        en:retrofit_needs_yes) echo "❌ An old manual install was detected and switching needs your confirmation, but there is no terminal to ask on; no files were touched. To agree, rerun with OPENAVER_YES=1 (or --yes)" ;;

        zh-TW:retrofit_done_fmt) echo "舊的程式檔都在 ~/OpenAver/%s/，確認沒問題可自行刪除" ;;
        zh-CN:retrofit_done_fmt) echo "旧的程序文件都在 ~/OpenAver/%s/，确认没问题可自行删除" ;;
        ja:retrofit_done_fmt) echo "古いプログラムファイルは ~/OpenAver/%s/ にあります。問題がなければご自身で削除してください" ;;
        en:retrofit_done_fmt) echo "Old program files are in ~/OpenAver/%s/ - delete them yourself once you have confirmed everything works" ;;

        zh-TW:archive_member_unexpected_fmt) echo "❌ 壓縮檔含有不該有的項目：%s" ;;
        zh-CN:archive_member_unexpected_fmt) echo "❌ 压缩包含有不该有的项目：%s" ;;
        ja:archive_member_unexpected_fmt) echo "❌ アーカイブに想定外の項目が含まれています：%s" ;;
        en:archive_member_unexpected_fmt) echo "❌ Archive contains an unexpected entry: %s" ;;

        zh-TW:extract_failed) echo "❌ 解壓縮失敗（可能是磁碟空間不足）" ;;
        zh-CN:extract_failed) echo "❌ 解压缩失败（可能是磁盘空间不足）" ;;
        ja:extract_failed) echo "❌ 展開に失敗しました（ディスク容量不足の可能性があります）" ;;
        en:extract_failed) echo "❌ Extraction failed (the disk may be full)" ;;

        zh-TW:running_foreign_no_tty) echo "❌ 偵測到舊的 OpenAver 服務還在執行，沒有終端機可以等你關閉。請先關閉它再重新執行安裝指令，沒有動任何檔案" ;;
        zh-CN:running_foreign_no_tty) echo "❌ 检测到旧的 OpenAver 服务仍在运行，没有终端可以等你关闭。请先关闭它再重新运行安装命令，没有改动任何文件" ;;
        ja:running_foreign_no_tty) echo "❌ 古い OpenAver サービスが実行中です。端末がなく待機できません。先に停止してからインストールコマンドを再実行してください。ファイルは一切触っていません" ;;
        en:running_foreign_no_tty) echo "❌ An old OpenAver service is still running and there is no terminal to wait on. Stop it first, then rerun the install command; no files were touched" ;;

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
    if [ -n "${STAGE:-}" ] && [ -d "$STAGE" ]; then
        case "$STAGE" in
            "$INSTALL_DIR"/.stage-*)
                rm -rf "$STAGE"
                ;;
        esac
    fi
    if [ "${INSTALL_DIR_CREATED:-0}" = "1" ]; then
        rmdir "$INSTALL_DIR" 2>/dev/null
    fi
    return 0
}

classify_install() {
    local item=""
    if [ -f "$INSTALL_DIR/app/core/version.py" ]; then
        echo "upgrade"
        return 0
    fi
    for item in app python openaver .prev; do
        if [ -e "$INSTALL_DIR/$item" ] || [ -L "$INSTALL_DIR/$item" ]; then
            echo "interrupted"
            return 0
        fi
    done
    if [ -e "$INSTALL_DIR/venv" ] || [ -L "$INSTALL_DIR/venv" ]; then
        echo "retrofit"
        return 0
    fi
    echo "fresh"
}

check_archive_members() {
    local listing="" line="" norm="" first="" second="" ok=1
    listing="$(tar tzf "$1")" || {
        echo "$(t archive_invalid)" >&2
        return 1
    }
    while IFS= read -r line; do
        norm="$line"
        while :; do
            case "$norm" in
                ./*) norm="${norm#./}" ;;
                *) break ;;
            esac
        done
        while :; do
            case "$norm" in
                */) norm="${norm%/}" ;;
                *) break ;;
            esac
        done
        case "$norm" in
            ""|.) continue ;;
        esac
        ok=1
        case "$norm" in
            /*|..|../*|*/..|*/../*) ok=0 ;;
        esac
        first="${norm%%/*}"
        if [ "$first" != "OpenAver" ]; then
            ok=0
        elif [ "$norm" != "$first" ]; then
            second="${norm#*/}"
            second="${second%%/*}"
            case "$second" in
                app|python|openaver) ;;
                *) ok=0 ;;
            esac
        fi
        if [ "$ok" -ne 1 ]; then
            printf "$(t archive_member_unexpected_fmt)\n" "$line" >&2
            return 1
        fi
    done <<EOF_MEMBERS
$listing
EOF_MEMBERS
    return 0
}

own_service_pids() {
    local p=""
    if [ -f "$INSTALL_DIR/run/openaver.pid" ]; then
        p="$(cat "$INSTALL_DIR/run/openaver.pid" 2>/dev/null)"
        case "$p" in
            ""|*[!0-9]*) ;;
            *) echo "$p" ;;
        esac
    fi
    if [ -f "$HOME/.config/systemd/user/openaver.service" ]; then
        if [ -z "${XDG_RUNTIME_DIR:-}" ] && [ -d "/run/user/$(id -u)" ]; then
            export XDG_RUNTIME_DIR="/run/user/$(id -u)"
        fi
        p="$(systemctl --user show openaver.service -p MainPID 2>/dev/null | sed -n 's/^MainPID=\([0-9][0-9]*\)$/\1/p' | head -1)"
        if [ -n "$p" ] && [ "$p" -gt 0 ] 2>/dev/null; then
            echo "$p"
        fi
    fi
    return 0
}

find_foreign_service() {
    local d="" pid="" cmd="" cwd="" own=""
    own="$(own_service_pids | tr '\n' ' ')"
    for d in /proc/[0-9]*; do
        pid="${d#/proc/}"
        if [ "$pid" = "$$" ]; then
            continue
        fi
        case " $own " in
            *" $pid "*) continue ;;
        esac
        cmd="$(tr '\0' ' ' 2>/dev/null < "$d/cmdline")" || continue
        case "$cmd" in
            *uvicorn*web.app:app*) ;;
            *) continue ;;
        esac
        cwd="$(readlink "$d/cwd" 2>/dev/null)" || continue
        case "$cwd" in
            "$INSTALL_DIR"|"$INSTALL_DIR"/*) return 0 ;;
        esac
    done
    return 1
}

# 只依本次跑自己記下的 OLD_MOVED／NEW_PLACED 還原（動態作用域：變數宣告在 install_linux）。
swap_rollback() {
    local item="" bad=0
    if [ "$STARTED_NEW" = "1" ] && [ -x "$INSTALL_DIR/openaver" ]; then
        "$INSTALL_DIR/openaver" stop >/dev/null 2>&1
    fi
    for item in $NEW_PLACED; do
        rm -rf "$INSTALL_DIR/$item" || bad=1
    done
    for item in $OLD_MOVED; do
        mv "$INSTALL_DIR/.prev/$item" "$INSTALL_DIR/" || bad=1
    done
    if [ "$PREV_MADE" = "1" ]; then
        rmdir "$INSTALL_DIR/.prev" || bad=1
    fi
    if [ "$AUTOSTART_TOUCHED" = "1" ]; then
        "$INSTALL_DIR/openaver" autostart on >/dev/null 2>&1 || bad=1
    fi
    if [ "$WAS_RUNNING" = "1" ]; then
        "$INSTALL_DIR/openaver" start >/dev/null 2>&1 || bad=1
    fi
    if [ "$bad" -ne 0 ]; then
        printf "$(t rollback_incomplete_fmt)\n" "$INSTALL_DIR" >&2
    else
        echo "$(t upgrade_rolled_back)" >&2
    fi
    return 0
}

OLD_LAYOUT_ITEMS=".coderabbit.yaml .coveragerc .gitattributes .github .gitignore AGENTS.md CHANGELOG.md CHANGELOG_ARCHIVE.md CODE_OF_CONDUCT.md CONTRIBUTING.md LICENSE OpenAver-Windows-Setup.bat README.md README_EN.md SECURITY.md build.py build_macos.py core dmm_prefix_table.json docs eslint.config.mjs install.ps1 install.sh locales maker_mapping.json package-lock.json package.json pyproject.toml pytest.ini requirements-test.txt requirements.txt run.sh scripts stylelint.config.js synology tests web windows venv"
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
    local install_kind=""
    local OLD_DIR_NAME=""
    local OLD_DIR=""
    local curl_rc=0
    local http_code=""
    local OPT_UPDATE=0
    local OLD_MOVED=""
    local NEW_PLACED=""
    local PREV_MADE=0
    local STARTED_NEW=0
    local WAS_RUNNING=0
    local AUTOSTART_TOUCHED=0
    local leftover_name=""
    local cur_ver=""
    local leftovers=""
    local entry=""
    # STAGE and INSTALL_DIR_CREATED must be global: EXIT trap runs after this function returns.
    STAGE=""
    INSTALL_DIR_CREATED=0

    if [ "${OPENAVER_YES:-}" = "1" ]; then
        ASSUME_YES=1
    fi
    while [ $# -gt 0 ]; do
        case "$1" in
            --yes)
                ASSUME_YES=1
                shift
                ;;
            --update)
                OPT_UPDATE=1
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

    install_kind="$(classify_install)"
    case "$install_kind" in
        fresh|retrofit)
            if [ "$OPT_UPDATE" -eq 1 ]; then
                echo "$(t update_not_installed)" >&2
                return 1
            fi
            ;;
    esac

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
        RELEASE_JSON="$(curl -sSL --connect-timeout 10 --max-time 30 -w '\n%{http_code}' "https://api.github.com/repos/$REPO/releases/tags/$OPT_VERSION")" || curl_rc=$?
        if [ "$curl_rc" -ne 0 ]; then
            echo "$(t github_connect_failed)" >&2
            return 1
        fi
        http_code="$(printf '%s\n' "$RELEASE_JSON" | tail -n 1)"
        RELEASE_JSON="$(printf '%s\n' "$RELEASE_JSON" | sed '$d')"
        case "$http_code" in
            2[0-9][0-9]) ;;
            404)
                printf "$(t no_linux_asset_fmt)\n" "$OPT_VERSION" >&2
                return 1
                ;;
            *)
                echo "$(t github_connect_failed)" >&2
                return 1
                ;;
        esac
        VERSION_LABEL="$OPT_VERSION"
        DOWNLOAD_URL="$(printf '%s\n' "$RELEASE_JSON" | grep -o "\"browser_download_url\": *\"[^\"]*Linux-${LINUX_ARCH}\\.tar\\.gz\"" | head -1 | cut -d'"' -f4)"
        if [ -z "$DOWNLOAD_URL" ]; then
            printf "$(t no_linux_asset_fmt)\n" "$OPT_VERSION" >&2
            return 1
        fi
    else
        echo "$(t checking_latest_version)"
        RELEASE_JSON="$(curl -fsSL --connect-timeout 10 --max-time 30 "https://api.github.com/repos/$REPO/releases/latest")" || {
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

    if [ "$install_kind" = "upgrade" ] && [ -z "$OPT_VERSION" ] && [ -z "${OPENAVER_TARBALL:-}" ] && \
       [ -x "$INSTALL_DIR/python/bin/python3" ] && [ -L "$INSTALL_DIR/openaver" ] && [ -e "$INSTALL_DIR/openaver" ] && \
       [ ! -e "$INSTALL_DIR/.prev" ] && [ ! -L "$INSTALL_DIR/.prev" ]; then
        cur_ver="$(sed -n 's/^__version__ *= *"\([^"]*\)".*/\1/p' "$INSTALL_DIR/app/core/version.py" 2>/dev/null | head -1)"
        if [ -n "$cur_ver" ] && [ "${VERSION_LABEL#v}" = "$cur_ver" ]; then
            printf "$(t already_latest_fmt)\n" "$cur_ver"
            return 0
        fi
    fi
    case "$install_kind" in
        retrofit)
            OLD_DIR_NAME=".old-install"
            if [ -e "$INSTALL_DIR/$OLD_DIR_NAME" ] || [ -L "$INSTALL_DIR/$OLD_DIR_NAME" ]; then
                OLD_DIR_NAME=".old-install-$(date +%Y%m%d-%H%M%S)"
                if [ -e "$INSTALL_DIR/$OLD_DIR_NAME" ] || [ -L "$INSTALL_DIR/$OLD_DIR_NAME" ]; then
                    OLD_DIR_NAME="$OLD_DIR_NAME-$$"
                fi
            fi
            OLD_DIR="$INSTALL_DIR/$OLD_DIR_NAME"
            printf "$(t retrofit_notice_fmt)\n" "$OLD_DIR_NAME"
            if [ "$ASSUME_YES" -ne 1 ]; then
                if { exec 3</dev/tty; } 2>/dev/null; then
                    printf "%s" "$(t retrofit_confirm_prompt)"
                    reply=""
                    IFS= read -r reply <&3 || reply=""
                    exec 3<&-
                    case "$reply" in
                        y|Y) ;;
                        *)
                            echo "$(t install_cancelled)"
                            return 0
                            ;;
                    esac
                else
                    echo "$(t retrofit_needs_yes)" >&2
                    return 1
                fi
            fi
            ;;
    esac

    trap '_linux_cleanup_stage' EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    if [ ! -d "$INSTALL_DIR" ]; then
        mkdir -p "$INSTALL_DIR" || return 1
        INSTALL_DIR_CREATED=1
    fi
    stage_candidate="$INSTALL_DIR/.stage-$(date +%s)-$$"
    mkdir "$stage_candidate" || return 1
    STAGE="$stage_candidate"

    if [ -n "$DOWNLOAD_URL" ]; then
        printf "$(t downloading_fmt)\n" "$VERSION_LABEL"
        if ! curl -fSL --progress-bar --connect-timeout 15 --max-time 3600 --speed-limit 1024 --speed-time 60 "$DOWNLOAD_URL" -o "$STAGE/openaver.tar.gz"; then
            echo "$(t download_failed)" >&2
            return 1
        fi
        TARBALL="$STAGE/openaver.tar.gz"
    fi

    printf "$(t installing_to_fmt)\n" "$INSTALL_DIR"
    check_archive_members "$TARBALL" || return 1
    if ! tar xzf "$TARBALL" -C "$STAGE"; then
        echo "$(t extract_failed)" >&2
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

    if [ -x "$INSTALL_DIR/openaver" ] && "$INSTALL_DIR/openaver" status >/dev/null 2>&1; then
        WAS_RUNNING=1
    fi
    if find_foreign_service; then
        if { exec 3</dev/tty; } 2>/dev/null; then
            while find_foreign_service; do
                echo ""
                echo "$(t app_running_warning)"
                echo "$(t app_running_close_continue_prompt)"
                reply=""
                IFS= read -r reply <&3 || reply="q"
                case "$reply" in
                    q|Q)
                        exec 3<&-
                        echo "$(t install_cancelled)"
                        return 0
                        ;;
                esac
            done
            exec 3<&-
        else
            echo "$(t running_foreign_no_tty)" >&2
            return 1
        fi
    fi

    if [ "$install_kind" = "retrofit" ]; then
        mkdir "$OLD_DIR" || {
            printf "$(t place_failed_fmt)\n" ".old-install" >&2
            return 1
        }
        for item in $OLD_LAYOUT_ITEMS; do
            if [ -e "$INSTALL_DIR/$item" ] || [ -L "$INSTALL_DIR/$item" ]; then
                if ! mv "$INSTALL_DIR/$item" "$OLD_DIR/"; then
                    printf "$(t place_failed_fmt)\n" "$item" >&2
                    return 1
                fi
            fi
        done
    fi

    if [ -e "$INSTALL_DIR/.prev" ] || [ -L "$INSTALL_DIR/.prev" ]; then
        leftover_name=".prev-$(date +%Y%m%d-%H%M%S)"
        if [ -e "$INSTALL_DIR/$leftover_name" ] || [ -L "$INSTALL_DIR/$leftover_name" ]; then
            leftover_name="$leftover_name-$$"
        fi
        if ! mv "$INSTALL_DIR/.prev" "$INSTALL_DIR/$leftover_name"; then
            printf "$(t place_failed_fmt)\n" ".prev" >&2
            return 1
        fi
    fi
    if [ "$WAS_RUNNING" = "1" ]; then
        if ! "$INSTALL_DIR/openaver" stop; then
            echo "$(t update_stop_failed)" >&2
            return 1
        fi
    fi
    if ! mkdir "$INSTALL_DIR/.prev"; then
        printf "$(t place_failed_fmt)\n" ".prev" >&2
        swap_rollback
        return 1
    fi
    PREV_MADE=1
    for item in app python openaver; do
        if [ -e "$INSTALL_DIR/$item" ] || [ -L "$INSTALL_DIR/$item" ]; then
            if ! mv "$INSTALL_DIR/$item" "$INSTALL_DIR/.prev/"; then
                printf "$(t place_failed_fmt)\n" "$item" >&2
                swap_rollback
                return 1
            fi
            OLD_MOVED="$OLD_MOVED $item"
        fi
    done
    for item in app python openaver; do
        if ! mv "$STAGE/OpenAver/$item" "$INSTALL_DIR/"; then
            printf "$(t place_failed_fmt)\n" "$item" >&2
            swap_rollback
            return 1
        fi
        NEW_PLACED="$NEW_PLACED $item"
    done

    "$INSTALL_DIR/openaver" _prepare || { swap_rollback; return 1; }

    if [ "$install_kind" = "upgrade" ]; then
        if [ -f "$HOME/.config/systemd/user/openaver.service" ]; then
            AUTOSTART_TOUCHED=1
            if ! "$INSTALL_DIR/openaver" autostart on; then
                swap_rollback
                return 1
            fi
        fi
        if [ "${OPENAVER_INSTALL_NO_START:-}" != "1" ]; then
            STARTED_NEW=1
            if ! "$INSTALL_DIR/openaver" start; then
                swap_rollback
                return 1
            fi
            if [ "$WAS_RUNNING" != "1" ]; then
                "$INSTALL_DIR/openaver" stop >/dev/null 2>&1
            fi
        fi
    fi
    if [ "$PREV_MADE" = "1" ]; then
        rm -rf "$INSTALL_DIR/.prev"
    fi

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
    if [ "$install_kind" = "retrofit" ]; then
        printf "$(t retrofit_done_fmt)\n" "$OLD_DIR_NAME"
    fi
    for entry in "$INSTALL_DIR"/.prev-* "$INSTALL_DIR"/.stage-*; do
        if { [ -e "$entry" ] || [ -L "$entry" ]; } && [ "$entry" != "$STAGE" ]; then
            leftovers="$leftovers ${entry##*/}"
        fi
    done
    if [ -n "$leftovers" ]; then
        printf "$(t leftover_notice_fmt)\n" "${leftovers# }"
    fi
    if [ "$install_kind" = "upgrade" ]; then
        if [ "${OPENAVER_INSTALL_NO_START:-}" != "1" ]; then
            "$INSTALL_DIR/openaver" url || return $?
        fi
        return 0
    fi

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
