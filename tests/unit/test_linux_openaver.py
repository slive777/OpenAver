"""linux/openaver：經符號連結的 subprocess 行為測試＋四語 key 集合。"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import threading
import textwrap
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
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
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["OPENAVER_INSTALL_LANG"] = "zh-TW"
    if extra_env:
        env.update(extra_env)
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


_FAKE_SYSTEMCTL = """#!/bin/bash
D="$(dirname "$0")"
echo "$*" >> "$D/systemctl.log"
verb=""
for a in "$@"; do case "$a" in -*) ;; *) verb="$a"; break ;; esac; done
[ "$verb" = show ] && echo "MainPID=0"
if [ "$verb" = is-active ]; then
    if [ -f "$D/active_out" ]; then cat "$D/active_out"; else echo active; fi
fi
rc=0
[ -f "$D/rc_$verb" ] && rc="$(cat "$D/rc_$verb")"
exit "$rc"
"""
_FAKE_LOGINCTL = """#!/bin/bash
D="$(dirname "$0")"
echo "$*" >> "$D/loginctl.log"
verb="$1"
[ "$verb" = show-user ] && { cat "$D/linger" 2>/dev/null; exit 0; }
rc=1
[ -f "$D/rc_$verb" ] && rc="$(cat "$D/rc_$verb")"
exit "$rc"
"""
_FAKE_SUDO = """#!/bin/bash
D="$(dirname "$0")"
echo "$*" >> "$D/sudo.log"
rc=1
[ -f "$D/rc_sudo" ] && rc="$(cat "$D/rc_sudo")"
exit "$rc"
"""


def _fakebin(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """PATH 前置 systemctl／loginctl／sudo 三個偽命令（缺一就會打到真正的 user manager）。"""
    fb = tmp_path / "fakebin"
    fb.mkdir(parents=True, exist_ok=True)
    for name, body in (("systemctl", _FAKE_SYSTEMCTL), ("loginctl", _FAKE_LOGINCTL), ("sudo", _FAKE_SUDO)):
        (fb / name).write_text(body, encoding="utf-8")
        (fb / name).chmod(0o755)
    (fb / "linger").write_text("Linger=yes\n", encoding="utf-8")
    return fb, {"PATH": f"{fb}:{os.environ['PATH']}"}


def _verbs(log: Path) -> list[str]:
    out = []
    for ln in log.read_text(encoding="utf-8").splitlines():
        words = [w for w in ln.split() if not w.startswith("-")]
        if words:
            out.append(words[0])
    return out


_NEEDS_SYSTEMD = pytest.mark.skipif(
    not Path("/run/systemd/system").is_dir(), reason="/run/systemd/system 不存在，無法走 systemd_usable 成功路徑"
)


def test_reset_password_without_layout_creates_nothing_and_explains(tmp_path):
    home, cli, stub_out = _setup_tree(tmp_path)
    _fb, env = _fakebin(tmp_path)
    r = _run_cli(home, cli, ["reset-password"], stub_out=stub_out, extra_env=env)
    assert r.returncode == 0, r.stderr
    assert "沒有密碼可以重設" in r.stdout
    assert not (home / "OpenAver" / "output").exists()


def test_reset_password_with_layout_and_service_stopped_marks_for_next_start(tmp_path):
    home, cli, stub_out = _setup_tree(tmp_path)
    _fb, env = _fakebin(tmp_path)
    out = home / "OpenAver" / "output"
    out.mkdir()
    (out / ".layout.json").write_text("{}", encoding="utf-8")
    r = _run_cli(home, cli, ["reset-password"], stub_out=stub_out, extra_env=env)
    assert r.returncode == 0, r.stderr
    assert (out / ".reset_access_auth").exists()
    assert "下次啟動生效" in r.stdout
    assert not stub_out.exists(), "不該啟動服務"
    assert not (home / "OpenAver" / "run" / "openaver.pid").exists()


def test_autostart_on_without_usable_systemd_exits_zero_and_says_start(tmp_path):
    home, cli, stub_out = _setup_tree(tmp_path)
    fb, env = _fakebin(tmp_path)
    (fb / "rc_show-environment").write_text("1", encoding="utf-8")
    r = _run_cli(home, cli, ["autostart", "on"], stub_out=stub_out, extra_env=env)
    assert r.returncode == 0, r.stderr
    assert "改用 openaver start" in r.stdout
    assert not (home / ".config" / "systemd" / "user" / "openaver.service").exists()


@_NEEDS_SYSTEMD
def test_autostart_on_writes_unit_with_required_fields(tmp_path):
    home, cli, stub_out = _setup_tree(tmp_path)
    fb, env = _fakebin(tmp_path)
    r = _run_cli(home, cli, ["autostart", "on"], stub_out=stub_out, extra_env=env)
    assert r.returncode == 0, r.stderr
    unit = (home / ".config" / "systemd" / "user" / "openaver.service").read_text(encoding="utf-8")
    lines = unit.splitlines()
    for want in (
        "[Unit]",
        "Description=OpenAver",
        "[Service]",
        "Type=exec",
        "ExecStart=%h/OpenAver/openaver run",
        "Restart=always",
        "RestartSec=3",
        "TimeoutStopSec=25",
        "KillMode=mixed",
        "StandardOutput=append:%h/OpenAver/logs/server.log",
        "StandardError=inherit",
        "[Install]",
        "WantedBy=default.target",
    ):
        assert want in lines, f"unit 缺整行 {want!r}"
    assert "network-online" not in unit
    assert not any(ln.startswith("After=") for ln in lines)
    assert "enable openaver.service" in (fb / "systemctl.log").read_text(encoding="utf-8")


@_NEEDS_SYSTEMD
def test_autostart_linger_failure_is_reported_and_status_keeps_warning(tmp_path):
    home, cli, stub_out = _setup_tree(tmp_path)
    fb, env = _fakebin(tmp_path)
    user = subprocess.run(["id", "-un"], capture_output=True, text=True, check=True).stdout.strip()
    (fb / "linger").write_text("Linger=no\n", encoding="utf-8")
    needle = f"sudo loginctl enable-linger {user}"

    r = _run_cli(home, cli, ["autostart", "on"], stub_out=stub_out, extra_env=env)
    assert r.returncode == 0, r.stderr
    assert needle in r.stdout
    assert f"enable-linger {user}" in (fb / "loginctl.log").read_text(encoding="utf-8")
    assert f"-n loginctl enable-linger {user}" in (fb / "sudo.log").read_text(encoding="utf-8")

    r = _run_cli(home, cli, ["status"], stub_out=stub_out, extra_env=env)
    assert needle in r.stdout

    (fb / "linger").write_text("Linger=yes\n", encoding="utf-8")
    r = _run_cli(home, cli, ["status"], stub_out=stub_out, extra_env=env)
    assert "enable-linger" not in r.stdout


def test_stop_and_restart_report_systemctl_stop_failure(tmp_path):
    home, cli, stub_out = _setup_tree(tmp_path)
    fb, env = _fakebin(tmp_path)
    unit_dir = home / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True)
    (unit_dir / "openaver.service").write_text("[Unit]\n", encoding="utf-8")
    (fb / "rc_stop").write_text("1", encoding="utf-8")

    r = _run_cli(home, cli, ["stop"], stub_out=stub_out, extra_env=env)
    assert r.returncode != 0
    assert "OpenAver 已停止" not in r.stdout
    assert r.stderr.strip()

    r = _run_cli(home, cli, ["restart"], stub_out=stub_out, extra_env=env)
    assert r.returncode != 0
    assert "start" not in _verbs(fb / "systemctl.log"), "停不掉就不該進 start"

    (fb / "rc_stop").write_text("0", encoding="utf-8")
    r = _run_cli(home, cli, ["stop"], stub_out=stub_out, extra_env=env)
    assert r.returncode == 0
    assert "OpenAver 已停止" in r.stdout


@_NEEDS_SYSTEMD
def test_autostart_on_stops_self_managed_daemon_then_starts_via_systemd(tmp_path):
    home, cli, stub_out = _setup_tree(tmp_path)
    fb, env = _fakebin(tmp_path)
    root = home / "OpenAver"

    class _Ok(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok","version":"9.9.9"}')

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), _Ok)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    (root / "openaver.conf").write_text(f"port={srv.server_address[1]}\n", encoding="utf-8")
    pid = _spawn(OURS_SLEEP)
    pidfile = root / "run" / "openaver.pid"
    pidfile.write_text(str(pid), encoding="utf-8")
    try:
        r = _run_cli(home, cli, ["autostart", "on"], stub_out=stub_out, extra_env=env)
        assert r.returncode == 0, r.stdout + r.stderr
        assert _wait_gone(pid), "自管行程應被停掉，不能脫離管理"
        assert not pidfile.exists()
        assert "start" in _verbs(fb / "systemctl.log"), "停掉後應改由 systemd 啟動"
    finally:
        srv.shutdown()
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            pass
        _wait_gone(pid)


def test_reset_password_reports_unknown_service_state_instead_of_next_start(tmp_path):
    home, cli, stub_out = _setup_tree(tmp_path)
    fb, env = _fakebin(tmp_path)
    unit_dir = home / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True)
    (unit_dir / "openaver.service").write_text("[Unit]\n", encoding="utf-8")
    out = home / "OpenAver" / "output"
    out.mkdir()
    (out / ".layout.json").write_text("{}", encoding="utf-8")
    (fb / "rc_is-active").write_text("1", encoding="utf-8")
    (fb / "active_out").write_text("", encoding="utf-8")

    r = _run_cli(home, cli, ["reset-password"], stub_out=stub_out, extra_env=env)
    assert r.returncode != 0
    assert "下次啟動生效" not in r.stdout
    assert "密碼保護已關閉" not in r.stdout
    assert r.stderr.strip()
    assert not (out / ".reset_access_auth").exists(), "狀態不明時不得留下重設標記，否則下次啟動會靜默關掉密碼"

    (fb / "rc_is-active").write_text("3", encoding="utf-8")
    (fb / "active_out").write_text("inactive\n", encoding="utf-8")
    r = _run_cli(home, cli, ["reset-password"], stub_out=stub_out, extra_env=env)
    assert r.returncode == 0
    assert "下次啟動生效" in r.stdout
    assert (out / ".reset_access_auth").exists(), "服務未啟動時應留下標記，下次啟動才會生效"


def test_start_does_not_report_started_when_port_answers_with_other_version_health(tmp_path):
    """服務已登記、conf 的 port 被別人（或別版 OpenAver）占走且 /api/health 也回 200：不得印已啟動。"""
    home, cli, stub_out = _setup_tree(tmp_path)
    _fb, env = _fakebin(tmp_path)
    unit_dir = home / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True)
    (unit_dir / "openaver.service").write_text("[Unit]\n", encoding="utf-8")

    class _Foreign(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok","version":"1.2.3"}')

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), _Foreign)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    (home / "OpenAver" / "openaver.conf").write_text(f"port={srv.server_address[1]}\n", encoding="utf-8")
    try:
        r = _run_cli(home, cli, ["start"], stub_out=stub_out, extra_env=env, timeout=90)
        assert r.returncode != 0, r.stdout
        assert "OpenAver 已啟動" not in r.stdout
        assert r.stderr.strip()
    finally:
        srv.shutdown()
