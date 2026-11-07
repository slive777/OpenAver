"""linux/openaver：經符號連結的 subprocess 行為測試＋四語 key 集合。"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT_SRC = REPO / "linux" / "openaver"
INSTALL_SH = REPO / "install.sh"
_LANGS = ("zh-TW", "zh-CN", "ja", "en")

OURS_SLEEP = 'exec -a "python3 -m uvicorn web.app:app" sleep 60'

_SH_TABLE_RE = re.compile(
    r'^[ \t]*case "\$\{LANG_KEY\}:\$1" in\n(.*?)\n[ \t]*esac\n',
    re.MULTILINE | re.DOTALL,
)
_SH_KEY_LINE_RE = re.compile(
    r'^[ \t]*(zh-TW|zh-CN|ja|en):([A-Za-z0-9_]+)\) echo "([^"]*)" ;;$',
    re.MULTILINE,
)
_DETECT_RE = re.compile(
    r'^[ \t]*detect_installer_lang\(\) \{\n(.*?)\n[ \t]*\}\n',
    re.MULTILINE | re.DOTALL,
)


def _alive(pid: int) -> bool:
    """True only for a live non-zombie process (Z in /proc/<pid>/stat = dead)."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as f:
            stat = f.read()
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return False
    # /proc/pid/stat: "pid (comm) state ..." — comm may contain spaces/parens
    rparen = stat.rfind(") ")
    if rparen < 0:
        return False
    state = stat[rparen + 2 : rparen + 3]
    if state == "Z":
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _spawn(cmd: str) -> int:
    """Spawn a grandchild (reaped by init) so death leaves no zombie for kill -0."""
    out = subprocess.run(
        ["bash", "-c", f"({cmd}) >/dev/null 2>&1 & echo $!"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    ).stdout
    time.sleep(0.3)
    return int(out.strip())


def _wait_gone(pid: int, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.1)
    return not _alive(pid)


def _setup_tree(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Build stub install tree. Returns (home, cli_symlink, stub_out)."""
    home = tmp_path / "home"
    root = home / "OpenAver"
    app = root / "app"
    linux_dir = app / "linux"
    core_dir = app / "core"
    py_bin = root / "python" / "bin"
    local_bin = home / ".local" / "bin"
    for d in (linux_dir, core_dir, py_bin, local_bin, root / "run", root / "logs"):
        d.mkdir(parents=True, exist_ok=True)

    (core_dir / "version.py").write_text('__version__ = "9.9.9"\n', encoding="utf-8")
    shutil.copy2(SCRIPT_SRC, linux_dir / "openaver")
    (linux_dir / "openaver").chmod(0o755)

    stub_out = tmp_path / "stub_out.txt"
    stub = py_bin / "python3"
    stub.write_text(
        "#!/bin/bash\n"
        '{ echo "CWD=$(pwd)"; echo "DATA=$OPENAVER_DATA_DIR";'
        ' echo "SERVER_ONLY=$OPENAVER_SERVER_ONLY";'
        ' echo "NOBYTECODE=$PYTHONDONTWRITEBYTECODE";'
        ' for a in "$@"; do echo "ARG=$a"; done; } > "$STUB_OUT"\n'
        "exit 0\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)

    # relative symlink: ~/OpenAver/openaver -> app/linux/openaver
    (root / "openaver").symlink_to("app/linux/openaver")
    # ~/.local/bin/openaver -> ~/OpenAver/openaver (absolute target is fine)
    (local_bin / "openaver").symlink_to(root / "openaver")

    return home, local_bin / "openaver", stub_out


def _run_cli(
    home: Path,
    cli: Path,
    args: list[str],
    *,
    stub_out: Path | None = None,
    cwd: Path | None = None,
    timeout: float = 30,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["OPENAVER_INSTALL_LANG"] = "zh-TW"
    if stub_out is not None:
        env["STUB_OUT"] = str(stub_out)
    work = cwd if cwd is not None else home.parent / "elsewhere"
    work.mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        [str(cli), *args],
        env=env,
        cwd=str(work),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def test_stop_leaves_process_alone_when_pid_file_points_to_someone_else(tmp_path):
    home, cli, stub_out = _setup_tree(tmp_path)
    pid = _spawn("sleep 60")
    try:
        pidfile = home / "OpenAver" / "run" / "openaver.pid"
        pidfile.parent.mkdir(parents=True, exist_ok=True)
        pidfile.write_text(str(pid), encoding="utf-8")

        r = _run_cli(home, cli, ["status"], stub_out=stub_out)
        assert r.returncode == 3

        r = _run_cli(home, cli, ["stop"], stub_out=stub_out)
        assert r.returncode == 0
        assert not pidfile.exists()
        assert _alive(pid)
    finally:
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            pass
        _wait_gone(pid)


def test_stop_terminates_our_daemon_and_status_follows(tmp_path):
    home, cli, stub_out = _setup_tree(tmp_path)
    pid = _spawn(OURS_SLEEP)
    try:
        pidfile = home / "OpenAver" / "run" / "openaver.pid"
        pidfile.parent.mkdir(parents=True, exist_ok=True)
        pidfile.write_text(str(pid), encoding="utf-8")

        r = _run_cli(home, cli, ["status"], stub_out=stub_out)
        assert r.returncode == 0

        r = _run_cli(home, cli, ["stop"], stub_out=stub_out)
        assert r.returncode == 0
        assert _wait_gone(pid), "行程應消失"
        assert not pidfile.exists(), "PID 檔應被刪"

        r = _run_cli(home, cli, ["status"], stub_out=stub_out)
        assert r.returncode == 3
    finally:
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            pass
        _wait_gone(pid)


@pytest.mark.parametrize("bad", ["80", "99999", "abc"])
def test_config_port_rejects_out_of_range_and_non_numeric(tmp_path, bad):
    home, cli, stub_out = _setup_tree(tmp_path)
    conf = home / "OpenAver" / "openaver.conf"
    r = _run_cli(home, cli, ["config", "port", bad], stub_out=stub_out)
    assert r.returncode != 0
    assert not conf.exists()


def test_config_port_value_reaches_run_and_runs_from_symlink(tmp_path):
    home, cli, stub_out = _setup_tree(tmp_path)
    conf = home / "OpenAver" / "openaver.conf"

    r = _run_cli(home, cli, ["config", "port", "50123"], stub_out=stub_out)
    assert r.returncode == 0
    assert conf.exists(), "openaver.conf 應存在"
    assert "port=50123" in conf.read_text(encoding="utf-8")
    assert "openaver restart" in (r.stdout + r.stderr)

    stub_out.write_text("", encoding="utf-8")
    r = _run_cli(home, cli, ["run"], stub_out=stub_out)
    assert r.returncode == 0
    recorded = stub_out.read_text(encoding="utf-8")
    assert "ARG=--port" in recorded
    assert "ARG=50123" in recorded
    assert "ARG=--host" in recorded
    assert "ARG=0.0.0.0" in recorded
    # CWD must resolve to home/OpenAver/app
    cwd_line = next(ln for ln in recorded.splitlines() if ln.startswith("CWD="))
    assert Path(cwd_line[4:]).resolve() == (home / "OpenAver" / "app").resolve()
    assert f"DATA={home / 'OpenAver' / 'output'}" in recorded
    assert "SERVER_ONLY=1" in recorded
    assert "NOBYTECODE=1" in recorded


def test_status_warns_when_conf_port_unreadable(tmp_path):
    """openaver.conf 存在但 port 不合法 → status 必須印警告（不靠子 shell 副作用）。"""
    home, cli, stub_out = _setup_tree(tmp_path)
    conf = home / "OpenAver" / "openaver.conf"
    conf.write_text("port=abc\n", encoding="utf-8")
    r = _run_cli(home, cli, ["status"], stub_out=stub_out)
    assert r.returncode == 3
    assert "警告：openaver.conf 格式無法辨識" in r.stdout


def test_openaver_language_keysets_equal_and_lang_detect_matches_install_sh():
    text = SCRIPT_SRC.read_text(encoding="utf-8")
    m = _SH_TABLE_RE.search(text)
    assert m is not None, "找到語言表區塊"
    keysets: dict[str, set[str]] = {}
    for lang, key, _val in _SH_KEY_LINE_RE.findall(m.group(1)):
        keysets.setdefault(lang, set()).add(key)
    assert set(keysets.keys()) == set(_LANGS), f"四語都抓得到，只抓到 {sorted(keysets.keys())}"
    reference = keysets["zh-TW"]
    assert len(reference) >= 20, "zh-TW key 數 ≥ 20（防空翻）"
    for lang in _LANGS:
        diff = keysets[lang].symmetric_difference(reference)
        assert not diff, f"{lang} 與 zh-TW key 集合不相等：{sorted(diff)}"

    det = _DETECT_RE.search(text)
    assert det is not None, "找到 detect_installer_lang 區塊"
    openaver_body = textwrap.dedent(det.group(1))
    install_text = INSTALL_SH.read_text(encoding="utf-8")
    inst = _DETECT_RE.search(install_text)
    assert inst is not None, "install.sh 找到 detect_installer_lang"
    install_body = textwrap.dedent(inst.group(1))
    assert openaver_body == install_body
    assert len(openaver_body.splitlines()) >= 10


def test_url_and_status_warn_only_when_conf_port_differs_from_listening(tmp_path):
    home, cli, stub_out = _setup_tree(tmp_path)
    root = home / "OpenAver"
    conf = root / "openaver.conf"

    # Independent listener: exec -a uvicorn..., body binds 127.0.0.1:0 and prints port
    listener_code = (
        "import socket,sys,time;"
        "s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);"
        "s.bind(('127.0.0.1',0));s.listen(1);"
        "print(s.getsockname()[1],flush=True);"
        "time.sleep(60)"
    )
    proc = subprocess.Popen(
        [
            "bash",
            "-c",
            f'exec -a "python3 -m uvicorn web.app:app" {sys.executable} -c {listener_code!r}',
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        assert proc.stdout is not None
        line = proc.stdout.readline()
        listen_port = int(line.strip())
        conf_port = listen_port + 1 if listen_port < 65535 else listen_port - 1
        conf.write_text(f"port={conf_port}\n", encoding="utf-8")
        pidfile = root / "run" / "openaver.pid"
        pidfile.write_text(str(proc.pid), encoding="utf-8")

        warn_needle = "設定已改為"
        r_url = _run_cli(home, cli, ["url"], stub_out=stub_out)
        assert warn_needle in r_url.stdout, "stdout 含 設定已改為"
        assert str(conf_port) in r_url.stdout
        assert str(listen_port) in r_url.stdout

        r_st = _run_cli(home, cli, ["status"], stub_out=stub_out)
        assert warn_needle in r_st.stdout, "stdout 含 設定已改為"

        # conf matches listening → no warning
        conf.write_text(f"port={listen_port}\n", encoding="utf-8")
        r_url2 = _run_cli(home, cli, ["url"], stub_out=stub_out)
        assert warn_needle not in r_url2.stdout
        r_st2 = _run_cli(home, cli, ["status"], stub_out=stub_out)
        assert warn_needle not in r_st2.stdout
    finally:
        try:
            os.kill(proc.pid, 9)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass
        _wait_gone(proc.pid)
