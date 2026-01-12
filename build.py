"""
OpenAver Windows 打包腳本
在 WSL/Linux 環境下打包出 Windows 可用的 ZIP

使用方式：
    python build.py

原理：
    1. 下載 Windows 嵌入式 Python
    2. 用 pip download 下載 Windows wheel 檔案
    3. 解壓 wheel 到 site-packages
    4. 打包成 ZIP
"""
import os
import sys
import shutil
import zipfile
import urllib.request
import subprocess
import tempfile
from pathlib import Path

# ============ 配置 ============

PYTHON_VERSION = "3.12.4"
PYTHON_EMBED_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"

# 專案結構
PROJECT_ROOT = Path(__file__).parent
BUILD_DIR = PROJECT_ROOT / "build"
DIST_DIR = PROJECT_ROOT / "dist"
CACHE_DIR = PROJECT_ROOT / ".build_cache"  # 緩存目錄（不會被清理）

# 需要複製的專案目錄/檔案
COPY_ITEMS = [
    "web",
    "core",
    "windows",
    "maker_mapping.json",
]

# 主要套件（會自動解析依賴）
PACKAGES = [
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
    "pywebview",
]


# ============ 工具函數 ============

def download_file(url: str, dest: Path) -> None:
    """下載檔案"""
    print(f"  下載: {url}")
    urllib.request.urlretrieve(url, dest)
    print(f"  完成: {dest.name}")


def extract_zip(zip_path: Path, dest_dir: Path) -> None:
    """解壓 ZIP"""
    print(f"  解壓: {zip_path.name}")
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(dest_dir)


def extract_wheel(wheel_path: Path, dest_dir: Path) -> None:
    """解壓 wheel 檔案到目標目錄"""
    with zipfile.ZipFile(wheel_path, 'r') as zf:
        for member in zf.namelist():
            # 跳過 .dist-info 以外的 metadata
            if member.endswith('/'):
                continue
            # 解壓到目標目錄
            zf.extract(member, dest_dir)


def extract_tar_gz(tar_path: Path, dest_dir: Path) -> None:
    """解壓 tar.gz 原始碼套件到目標目錄（只複製 Python 模組）"""
    import tarfile
    with tarfile.open(tar_path, 'r:gz') as tf:
        # 找出套件目錄（通常是 package_name-version/package_name/）
        members = tf.getnames()
        # 找出實際的 Python 套件目錄
        for member in members:
            parts = member.split('/')
            if len(parts) >= 2 and not parts[1].endswith('.egg-info') and not parts[1].startswith('.'):
                # 可能是套件目錄
                pkg_name = parts[1]
                if any(m.startswith(f"{parts[0]}/{pkg_name}/") and m.endswith('.py') for m in members):
                    # 確認是 Python 套件
                    pkg_prefix = f"{parts[0]}/{pkg_name}/"
                    for m in tf.getmembers():
                        if m.name.startswith(pkg_prefix):
                            # 調整路徑：移除頂層目錄
                            m.name = m.name[len(parts[0]) + 1:]
                            tf.extract(m, dest_dir)
                    return


# ============ 打包步驟 ============

def clean_build():
    """清理舊的建置目錄"""
    print("\n[1/6] 清理舊建置...")
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir(parents=True)


def download_embedded_python():
    """下載嵌入式 Python（使用緩存）"""
    print("\n[2/6] 準備嵌入式 Python...")

    python_dir = BUILD_DIR / "OpenAver" / "python"
    python_dir.mkdir(parents=True)

    # 檢查緩存
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached_zip = CACHE_DIR / f"python-{PYTHON_VERSION}-embed-amd64.zip"

    if cached_zip.exists():
        print(f"  使用緩存: {cached_zip.name}")
    else:
        print("  下載中（首次會較慢）...")
        download_file(PYTHON_EMBED_URL, cached_zip)

    # 從緩存解壓
    extract_zip(cached_zip, python_dir)

    # 修改 _pth 檔案以啟用 site-packages
    pth_files = list(python_dir.glob("python*._pth"))
    if not pth_files:
        raise RuntimeError("找不到 ._pth 檔案")

    pth_file = pth_files[0]
    pth_name = pth_file.stem  # e.g., "python312"

    pth_content = f"""{pth_name}.zip
.
Lib/site-packages
../app
import site
"""
    pth_file.write_text(pth_content)
    print(f"  已修改: {pth_file.name}")

    return python_dir


def get_all_dependencies():
    """從現有 venv 獲取完整依賴列表"""
    result = subprocess.run(
        [sys.executable, "-m", "pip", "freeze"],
        capture_output=True, text=True
    )
    deps = []
    for line in result.stdout.strip().split('\n'):
        if '==' in line:
            pkg_name = line.split('==')[0].strip()
            deps.append(pkg_name)
    return deps


def download_and_install_packages(python_dir: Path):
    """下載 Windows wheel 並解壓到 site-packages（使用緩存）"""
    print("\n[3/6] 準備依賴套件...")

    site_packages = python_dir / "Lib" / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)

    # 使用緩存目錄存放 wheel
    wheels_dir = CACHE_DIR / "wheels"
    wheels_dir.mkdir(parents=True, exist_ok=True)

    # 從現有 venv 獲取所有已安裝的套件
    all_deps = get_all_dependencies()
    # 加入 pywebview（可能不在 venv 中）
    if "pywebview" not in [d.lower() for d in all_deps]:
        all_deps.append("pywebview")

    # 額外依賴（手動補充 Windows 專用套件）
    extra_deps = [
        "bottle", "proxy-tools", "clr_loader", "pythonnet",
        "win32-setctime", "colorama",
    ]
    all_deps.extend(extra_deps)

    # 檢查已緩存的套件
    cached_files = set(f.stem.split('-')[0].lower().replace('_', '-') for f in wheels_dir.glob("*.*"))
    to_download = [pkg for pkg in all_deps if pkg.lower().replace('_', '-') not in cached_files]

    if to_download:
        print(f"  需下載 {len(to_download)} 個新套件（已緩存 {len(all_deps) - len(to_download)} 個）")
        for pkg in to_download:
            # 嘗試下載 Windows wheel
            pip_cmd = [
                sys.executable, "-m", "pip", "download",
                "--dest", str(wheels_dir),
                "--platform", "win_amd64",
                "--python-version", "3.12",
                "--only-binary", ":all:",
                "--no-deps",
                pkg,
            ]
            result = subprocess.run(pip_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                # 嘗試不限平台（純 Python 套件）
                pip_cmd = [
                    sys.executable, "-m", "pip", "download",
                    "--dest", str(wheels_dir),
                    "--no-deps",
                    pkg,
                ]
                subprocess.run(pip_cmd, capture_output=True, text=True)
    else:
        print(f"  全部 {len(all_deps)} 個套件已緩存")

    # 解壓所有套件到 site-packages
    print("\n[4/6] 安裝套件到 site-packages...")
    wheel_files = list(wheels_dir.glob("*.whl"))
    tar_files = list(wheels_dir.glob("*.tar.gz"))
    print(f"  找到 {len(wheel_files)} 個 wheel, {len(tar_files)} 個 tar.gz")

    for wheel_file in wheel_files:
        print(f"  安裝: {wheel_file.name}")
        extract_wheel(wheel_file, site_packages)

    for tar_file in tar_files:
        print(f"  安裝: {tar_file.name}")
        extract_tar_gz(tar_file, site_packages)

    # 保留緩存（不清理 wheels_dir）


def copy_project_files():
    """複製專案檔案"""
    print("\n[5/6] 複製專案檔案...")

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

    # 複製 config.default.json（預設設定範本）
    # 注意：不複製 config.json，讓目標環境保留自己的設定
    config_default_src = PROJECT_ROOT / "web" / "config.default.json"
    config_default_dst = app_dir / "web" / "config.default.json"
    if config_default_src.exists():
        shutil.copy2(config_default_src, config_default_dst)
        print("  複製檔案: config.default.json")


def create_launcher_scripts():
    """建立啟動腳本和說明檔"""
    print("  建立啟動腳本...")

    root_dir = BUILD_DIR / "OpenAver"

    # OpenAver.bat - 顯示簡單日誌後用 pythonw.exe 啟動（無控制台）
    bat_content = '''@echo off
cd /d "%~dp0"
echo OpenAver starting...
echo Window will appear shortly...
start "" "python\\pythonw.exe" "app\\windows\\standalone.py"
ping -n 3 127.0.0.1 >nul
'''
    (root_dir / "OpenAver.bat").write_text(bat_content, encoding='utf-8')

    # OpenAver_Debug.bat - 有控制台版本（用於調試）
    debug_bat_content = '''@echo off
cd /d "%~dp0"
"python\\python.exe" "app\\windows\\standalone.py"
pause
'''
    (root_dir / "OpenAver_Debug.bat").write_text(debug_bat_content, encoding='utf-8')

    # README.txt
    readme_content = '''OpenAver - JAV 影片元數據管理工具
====================================

使用方法：
1. 雙擊 OpenAver.bat 啟動應用程式
2. 如遇問題，請使用 OpenAver_Debug.bat 查看錯誤訊息

系統需求：
- Windows 10/11 64位元
- 網路連線（用於搜尋資料）

注意事項：
- 首次啟動可能需要較長時間載入
- 設定檔儲存於 app\\web\\config.json
'''
    (root_dir / "README.txt").write_text(readme_content, encoding='utf-8')

    print("  已建立: OpenAver.bat, OpenAver_Debug.bat, README.txt")


def create_zip_package():
    """打包成 ZIP"""
    print("\n[6/6] 打包成 ZIP...")

    DIST_DIR.mkdir(parents=True, exist_ok=True)

    zip_name = "OpenAver-Windows-x64"
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
    print("OpenAver Windows 打包工具")
    print("=" * 50)

    try:
        clean_build()
        python_dir = download_embedded_python()
        download_and_install_packages(python_dir)
        copy_project_files()
        create_launcher_scripts()
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
