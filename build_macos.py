"""
OpenAver macOS 打包腳本
在 macOS 環境下打包出 Apple Silicon (arm64) 可用的 ZIP

使用方式：
    python build_macos.py

原理：
    1. 下載 python-build-standalone (aarch64-apple-darwin)
    2. 用 pip install 安裝依賴套件
    3. 複製專案檔案
    4. 打包成 ZIP
"""
import os
import sys
import shutil
import tarfile
import urllib.request
import subprocess
import platform
from pathlib import Path

# ============ 配置 ============

# python-build-standalone 版本 (從 GitHub releases 獲取)
PYTHON_VERSION = "3.12"
PYTHON_BUILD_DATE = "20241016"  # 發布日期
PYTHON_STANDALONE_URL = f"https://github.com/indygreg/python-build-standalone/releases/download/{PYTHON_BUILD_DATE}/cpython-{PYTHON_VERSION}.7+{PYTHON_BUILD_DATE}-aarch64-apple-darwin-install_only.tar.gz"

# 備用 URL（如果上面的不行）
PYTHON_STANDALONE_URL_ALT = "https://github.com/indygreg/python-build-standalone/releases/download/20240909/cpython-3.12.6+20240909-aarch64-apple-darwin-install_only.tar.gz"

# 專案結構
PROJECT_ROOT = Path(__file__).parent
BUILD_DIR = PROJECT_ROOT / "build_macos"
DIST_DIR = PROJECT_ROOT / "dist"
CACHE_DIR = PROJECT_ROOT / ".build_cache_macos"

# 需要複製的專案目錄/檔案
COPY_ITEMS = [
    "web",
    "core",
    "windows",  # 包含 standalone.py
    "maker_mapping.json",
]

# 共用套件
PACKAGES_COMMON = [
    "fastapi",
    "uvicorn[standard]",
    "jinja2",
    "python-multipart",
    "requests",
    "beautifulsoup4",
    "lxml",
    "jvav",
    "curl_cffi",
    "websockets",
    "pillow",
    "httpx",
]

# macOS 專用套件
PACKAGES_MACOS = [
    "pywebview",
    "pyobjc-core",
    "pyobjc-framework-Cocoa",
    "pyobjc-framework-WebKit",
]


# ============ 工具函數 ============

def download_file(url: str, dest: Path) -> bool:
    """下載檔案"""
    print(f"  下載: {url}")
    try:
        urllib.request.urlretrieve(url, dest)
        print(f"  完成: {dest.name}")
        return True
    except Exception as e:
        print(f"  失敗: {e}")
        return False


def extract_tar_gz(tar_path: Path, dest_dir: Path) -> None:
    """解壓 tar.gz"""
    print(f"  解壓: {tar_path.name}")
    with tarfile.open(tar_path, 'r:gz') as tf:
        tf.extractall(dest_dir)


# ============ 打包步驟 ============

def clean_build():
    """清理舊的建置目錄"""
    print("\n[1/7] 清理舊建置...")
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir(parents=True)


def download_python_standalone():
    """下載 python-build-standalone"""
    print("\n[2/7] 準備 Python (python-build-standalone)...")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached_tar = CACHE_DIR / f"python-{PYTHON_VERSION}-aarch64-apple-darwin.tar.gz"

    if cached_tar.exists():
        print(f"  使用緩存: {cached_tar.name}")
    else:
        print("  下載中（首次會較慢）...")
        if not download_file(PYTHON_STANDALONE_URL, cached_tar):
            print("  嘗試備用 URL...")
            if not download_file(PYTHON_STANDALONE_URL_ALT, cached_tar):
                raise RuntimeError("無法下載 python-build-standalone")

    # 解壓到 build 目錄
    python_extract_dir = BUILD_DIR / "OpenAver"
    python_extract_dir.mkdir(parents=True)
    extract_tar_gz(cached_tar, python_extract_dir)

    # python-build-standalone 解壓後的結構是 python/bin/python3
    python_dir = python_extract_dir / "python"
    if not python_dir.exists():
        raise RuntimeError(f"解壓後找不到 python 目錄: {python_dir}")

    print(f"  Python 已準備: {python_dir}")
    return python_dir


def install_packages(python_dir: Path):
    """安裝依賴套件"""
    print("\n[3/7] 安裝依賴套件...")

    python_path = python_dir / "bin" / "python3"

    # 確保 pip 可用
    print("  確保 pip 可用...")
    subprocess.run([str(python_path), "-m", "ensurepip", "--upgrade"], capture_output=True)
    subprocess.run([str(python_path), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], capture_output=True)

    all_packages = PACKAGES_COMMON + PACKAGES_MACOS
    print(f"  需安裝 {len(all_packages)} 個套件")

    # 使用 python -m pip install 安裝所有套件
    cmd = [
        str(python_path), "-m", "pip", "install",
        "--upgrade",
        "--no-warn-script-location",
    ] + all_packages

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  警告: 部分套件安裝失敗")
        print(result.stderr[:500])
    else:
        print("  所有套件安裝完成")


def copy_project_files():
    """複製專案檔案"""
    print("\n[4/7] 複製專案檔案...")

    app_dir = BUILD_DIR / "OpenAver" / "app"
    app_dir.mkdir(parents=True)

    for item in COPY_ITEMS:
        src = PROJECT_ROOT / item
        dst = app_dir / item

        if src.is_dir():
            print(f"  複製目錄: {item}")
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns(
                "__pycache__", "*.pyc", ".git", ".gitignore", "config.json"
            ))
        elif src.is_file():
            print(f"  複製檔案: {item}")
            shutil.copy2(src, dst)

    # 複製範例檔案
    samples_src = PROJECT_ROOT / "tests" / "samples" / "basic"
    samples_dst = BUILD_DIR / "OpenAver" / "教學檔案"
    if samples_src.exists():
        shutil.copytree(samples_src, samples_dst)
        print("  複製目錄: 教學檔案")


def create_launcher_scripts():
    """建立啟動腳本"""
    print("\n[5/7] 建立啟動腳本...")

    root_dir = BUILD_DIR / "OpenAver"

    # OpenAver.command - 雙擊執行的啟動腳本
    command_content = '''#!/bin/bash
cd "$(dirname "$0")"

echo "=============================="
echo "   OpenAver Starting..."
echo "=============================="
echo ""

# 設置 PYTHONPATH
export PYTHONPATH="$(pwd)/app:$PYTHONPATH"

# 使用 PyWebView 啟動
./python/bin/python3 -c "
import sys
sys.path.insert(0, 'app')
from windows.standalone import main
main()
"
'''

    # README.txt
    readme_content = '''OpenAver - JAV Metadata Manager
====================================

Usage:
1. Double-click OpenAver.command to launch
2. On first run, right-click and select "Open" to bypass Gatekeeper

Requirements:
- macOS 13+ (Ventura or later)
- Apple Silicon (M1/M2/M3/M4)

Notes:
- This is an Alpha release. Please report issues!
- Config: app/web/config.json
- GitHub: https://github.com/peacepenguin/OpenAver/issues
'''

    # MACOS_ALPHA_README.txt
    alpha_readme_content = '''===============================================
  OpenAver macOS - Alpha Test Version
===============================================

NOTICE: This is an alpha release. Please report
any issues to GitHub.

[First Run - IMPORTANT]
1. Right-click OpenAver.command
2. Select "Open"
3. Click "Open" in the dialog

This is required by macOS security. Only needed once.

[Known Limitations]
- Not signed by Apple (security warning expected)
- Only tested on macOS 13+ with Apple Silicon
- Please report issues!

[Support]
GitHub: https://github.com/peacepenguin/OpenAver/issues
'''

    # 寫入檔案
    command_file = root_dir / "OpenAver.command"
    command_file.write_text(command_content, encoding='utf-8')
    # 設置可執行權限
    os.chmod(command_file, 0o755)

    (root_dir / "README.txt").write_text(readme_content, encoding='utf-8')
    (root_dir / "MACOS_ALPHA_README.txt").write_text(alpha_readme_content, encoding='utf-8')

    print("  Created: OpenAver.command, README.txt, MACOS_ALPHA_README.txt")


def optimize_package():
    """優化打包體積"""
    print("\n[6/7] 優化打包體積...")

    app_dir = BUILD_DIR / "OpenAver"

    # 刪除 __pycache__ 和 .pyc
    pycache_count = 0
    for pycache in app_dir.rglob("__pycache__"):
        if pycache.is_dir():
            shutil.rmtree(pycache)
            pycache_count += 1

    # 刪除 .dist-info
    dist_info_count = 0
    for dist_info in app_dir.rglob("*.dist-info"):
        if dist_info.is_dir():
            shutil.rmtree(dist_info)
            dist_info_count += 1

    print(f"  刪除 {pycache_count} 個 __pycache__, {dist_info_count} 個 .dist-info")


def create_zip_package():
    """打包成 ZIP"""
    print("\n[7/7] 打包成 ZIP...")

    # 讀取版本號
    sys.path.insert(0, str(PROJECT_ROOT))
    from core.version import VERSION

    DIST_DIR.mkdir(parents=True, exist_ok=True)

    zip_name = f"OpenAver-v{VERSION}-macOS-arm64-alpha"
    zip_path = DIST_DIR / f"{zip_name}.zip"

    # 刪除舊的 ZIP
    if zip_path.exists():
        zip_path.unlink()

    # 建立 ZIP
    shutil.make_archive(
        str(DIST_DIR / zip_name),
        'zip',
        BUILD_DIR,
        "OpenAver"
    )

    # 計算檔案大小
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"  完成: {zip_path.name} ({size_mb:.1f} MB)")

    return zip_path


def main():
    """主程序"""
    print("=" * 50)
    print("OpenAver macOS 打包工具 (Alpha)")
    print("=" * 50)

    # 檢查是否在 macOS 上執行
    if sys.platform != 'darwin':
        print("\n錯誤: 此腳本只能在 macOS 上執行")
        sys.exit(1)

    # 檢查架構
    if platform.machine() != 'arm64':
        print(f"\n錯誤: 此腳本只支援 Apple Silicon (arm64)，目前: {platform.machine()}")
        sys.exit(1)

    try:
        clean_build()
        python_dir = download_python_standalone()
        install_packages(python_dir)
        copy_project_files()
        create_launcher_scripts()
        optimize_package()
        zip_path = create_zip_package()

        print("\n" + "=" * 50)
        print("打包完成！")
        print(f"輸出檔案: {zip_path}")
        print("=" * 50)

    except Exception as e:
        print(f"\n錯誤: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
