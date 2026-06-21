#!/bin/bash
set -e

REPO="slive777/OpenAver"
INSTALL_DIR="$HOME/OpenAver"

echo ""
echo "=============================="
echo "   OpenAver 安裝程式"
echo "=============================="
echo ""

# --- 偵測 OS ---
if [[ "$(uname)" != "Darwin" ]]; then
    echo "❌ 此腳本僅支援 macOS"
    echo "   Linux 目前沒有打包版本"
    exit 1
fi

# --- 偵測架構 ---
ARCH=$(uname -m)
if [[ "$ARCH" != "arm64" ]]; then
    echo "❌ 目前僅支援 Apple Silicon (M1/M2/M3/M4)"
    echo "   偵測到架構: $ARCH"
    exit 1
fi

# --- OpenAver 執行中偵測 ---
# macOS rm 對 advisory lock 不會 fail，故 rm 成敗不是權威信號，pgrep 才是。
is_openaver_running() {
    pgrep -f "$INSTALL_DIR/OpenAver.command" > /dev/null 2>&1 || \
    pgrep -f "$INSTALL_DIR/python/bin" > /dev/null 2>&1
}

# 提醒關閉並等待（Enter 重試 / q 取消），不強殺；不必重跑整條指令
wait_openaver_closed() {
    while is_openaver_running; do
        echo ""
        echo "⚠️  OpenAver 目前正在執行，無法覆蓋安裝。"
        echo "   請關閉 OpenAver 後，按 Enter 繼續（或輸入 q 取消）"
        local REPLY
        read -r REPLY < /dev/tty
        if [[ "$REPLY" == "q" || "$REPLY" == "Q" ]]; then
            echo "取消安裝"
            exit 0
        fi
    done
}

# --- 查詢最新版本 ---
echo "🔍 查詢最新版本..."
RELEASE_JSON=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest") || {
    echo "❌ 無法連線到 GitHub，請檢查網路"
    exit 1
}

VERSION=$(echo "$RELEASE_JSON" | grep -o '"tag_name": *"[^"]*"' | head -1 | cut -d'"' -f4)
DOWNLOAD_URL=$(echo "$RELEASE_JSON" | grep -o '"browser_download_url": *"[^"]*macOS-arm64[^"]*\.zip"' | head -1 | cut -d'"' -f4)

if [[ -z "$DOWNLOAD_URL" ]]; then
    echo "❌ 找不到 macOS 下載連結"
    exit 1
fi

echo "   最新版本: $VERSION"

# --- 檢查現有安裝 ---
if [[ -d "$INSTALL_DIR" ]]; then
    echo ""
    echo "⚠️  已偵測到現有安裝: $INSTALL_DIR"
    read -p "   是否覆蓋安裝？(y/N) " -n 1 -r REPLY < /dev/tty
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "取消安裝"
        exit 0
    fi

    # 下載前提早偵測：OpenAver 在跑就先擋，省得白下載才被卡
    wait_openaver_closed
fi

# --- 下載 ---
echo ""
echo "📦 下載 $VERSION..."
TMP_DIR=$(mktemp -d)
TMP_ZIP="$TMP_DIR/OpenAver.zip"
curl -fSL --progress-bar "$DOWNLOAD_URL" -o "$TMP_ZIP"

# --- 清除舊版 embedded Python（避免套件混版）---
# macOS rm 對 advisory lock 不會 fail，必須事前用 pgrep 攔截，否則會悄悄混版。
# 權威信號＝pgrep；仍在跑就提醒關閉並等待（不重跑指令、不強殺）後再 rm。
if [[ -d "$INSTALL_DIR/python" ]]; then
    wait_openaver_closed
    echo "🧹 清除舊版 Python runtime..."
    rm -rf "$INSTALL_DIR/python"
fi

# --- 解壓安裝（覆蓋程式檔案，保留用戶資料）---
echo "📂 安裝到 $INSTALL_DIR..."
unzip -o -q "$TMP_ZIP" -d "$HOME"

# --- 移除 macOS 安全限制 ---
echo "🔓 移除 macOS 安全限制..."
xattr -dr com.apple.quarantine "$INSTALL_DIR" 2>/dev/null || true
chmod +x "$INSTALL_DIR/OpenAver.command"

# --- 清理暫存 ---
rm -rf "$TMP_DIR"

# --- 完成 ---
echo ""
echo "✅ 安裝完成！"
echo ""
echo "   啟動方式："
echo "   1. 雙擊 ~/OpenAver/OpenAver.command"
echo "   2. 或在 Terminal 執行: ~/OpenAver/OpenAver.command"
echo ""
