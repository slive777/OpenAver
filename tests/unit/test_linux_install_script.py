"""TASK-194-T5a/T5b-i/T5b-ii: install.sh Linux 分支（偵測擋下／全新安裝就位／改裝／PREPARE 失敗／升級換位與還原）。"""

from __future__ import annotations

import hashlib
import contextlib
import io
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = REPO_ROOT / "install.sh"


def _write_exec(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _make_fakebin(
    fakebin: Path,
    *,
    arch: str = "x86_64",
    ldd_body: str = "ldd (Debian GLIBC 2.28-10) 2.28\n",
    ldd_rc: int = 0,
    glibc: str = "2.28",
    long_bit: str = "64",
    curl_flag: Path,
    with_autostart_fakes: bool = False,
    tar_log: Path | None = None,
    tar_fail_extract: bool = False,
    mv_log: Path | None = None,
    curl_serves: Path | None = None,
    curl_release: tuple[str, Path] | None = None,
) -> None:
    fakebin.mkdir(parents=True, exist_ok=True)
    for stale in fakebin.iterdir():
        stale.unlink()
    if mv_log is not None:
        _write_exec(
            fakebin / "mv",
            "#!/bin/bash\n"
            'if [ -n "${MV_COUNT_FILE:-}" ]; then\n'
            '  n=$(( $(cat "$MV_COUNT_FILE" 2>/dev/null || echo 0) + 1 ))\n'
            '  echo "$n" > "$MV_COUNT_FILE"\n'
            f'  printf "%s\\t%s\\n" "$PPID" "$*" >> "{mv_log}"\n'
            '  if [ "${MV_KILL_AT:-}" = "$n" ]; then kill -"${MV_SIGNAL:-9}" "$PPID"; [ -z "${MV_SIGNAL:-}" ] && exit 1; fi\n'
            "fi\n"
            f'exec {shutil.which("mv")} "$@"\n',
        )
    if tar_log is not None:
        fail = (
            'if [ "${1:-}" = "xzf" ]; then\n'
            '  while [ $# -gt 0 ]; do\n'
            '    if [ "$1" = "-C" ]; then printf x > "$2/partial-residue"; fi\n'
            "    shift\n"
            "  done\n"
            "  exit 2\n"
            "fi\n"
        )
        _write_exec(
            fakebin / "tar",
            "#!/bin/bash\n"
            f'printf "%s\\n" "${{1:-}}" >> "{tar_log}"\n'
            + (fail if tar_fail_extract else "")
            + f'exec {shutil.which("tar")} "$@"\n',
        )
    _write_exec(
        fakebin / "uname",
        "#!/bin/bash\n"
        'if [ "${1:-}" = "-m" ]; then printf "%s\\n" '
        f'"{arch}"; exit 0; fi\n'
        'printf "Linux\\n"\n',
    )
    _write_exec(
        fakebin / "ldd",
        "#!/bin/bash\n"
        f"cat <<'EOF'\n{ldd_body}EOF\n"
        f"exit {ldd_rc}\n",
    )
    _write_exec(
        fakebin / "getconf",
        "#!/bin/bash\n"
        'if [ "${1:-}" = "GNU_LIBC_VERSION" ]; then\n'
        f'  printf "glibc {glibc}\\n"\n'
        "  exit 0\n"
        "fi\n"
        'if [ "${1:-}" = "LONG_BIT" ]; then\n'
        f'  printf "{long_bit}\\n"\n'
        "  exit 0\n"
        "fi\n"
        "exit 1\n",
    )
    serve = ""
    if curl_serves is not None:
        serve = (
            'has=0; last=""\n'
            'for a in "$@"; do [ "$a" = "-fsSL" ] && has=1; last="$a"; done\n'
            'if [ "$has" = 1 ] && [ "$last" = '
            '"https://raw.githubusercontent.com/slive777/OpenAver/main/install.sh" ]; then\n'
            f'  cat "{curl_serves}"; exit 0\n'
            "fi\n"
        )
    if curl_release is not None:
        tag, tarball = curl_release
        serve += (
            'out=""; prev=""\n'
            'for a in "$@"; do [ "$prev" = "-o" ] && out="$a"; prev="$a"; last="$a"; done\n'
            'if [ "$last" = "https://api.github.com/repos/slive777/OpenAver/releases/latest" ]; then\n'
            f"  printf '{{\"tag_name\": \"v{tag}\", \"assets\": [{{\"browser_download_url\": "
            f"\"https://dl.invalid/OpenAver-v{tag}-Linux-x86_64.tar.gz\"}}]}}\\n'; exit 0\n"
            "fi\n"
            f'case " $* " in *" https://dl.invalid/"*) cp "{tarball}" "$out"; exit 0 ;; esac\n'
        )
    _write_exec(
        fakebin / "curl",
        "#!/bin/bash\n" + serve + f': > "{curl_flag}"\n'
        "exit 99\n",
    )
    if with_autostart_fakes:
        _write_exec(
            fakebin / "systemctl",
            "#!/bin/bash\n"
            'for a in "$@"; do\n'
            '  if [ "$a" = "show-environment" ]; then exit 1; fi\n'
            "done\n"
            "exit 0\n",
        )
        _write_exec(fakebin / "loginctl", "#!/bin/bash\nexit 0\n")
        _write_exec(fakebin / "sudo", "#!/bin/bash\nexit 1\n")


def _add_tree_to_tar(tar: tarfile.TarFile, src: Path, arc_prefix: str) -> None:
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        rel_dir = Path(dirpath).relative_to(src)
        arc_dir = arc_prefix if rel_dir == Path(".") else f"{arc_prefix}/{rel_dir.as_posix()}"
        info = tarfile.TarInfo(arc_dir)
        info.type = tarfile.DIRTYPE
        info.mode = 0o755
        tar.addfile(info)
        for name in filenames:
            if name.endswith(".pyc"):
                continue
            fp = Path(dirpath) / name
            arc = f"{arc_dir}/{name}"
            ti = tar.gettarinfo(str(fp), arcname=arc)
            ti.mode = fp.stat().st_mode & 0o777
            with fp.open("rb") as fh:
                tar.addfile(ti, fh)


@pytest.fixture(scope="module")
def stub_tarball(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build a one-shot Linux stub tarball with relative openaver symlink."""
    out = tmp_path_factory.mktemp("t5a-tarball") / "OpenAver-Linux-x86_64.tar.gz"
    staging = tmp_path_factory.mktemp("t5a-stage-src")
    oa = staging / "OpenAver"
    app = oa / "app"
    (app / "linux").mkdir(parents=True)
    (app / "scripts").mkdir(parents=True)
    (app / "web").mkdir(parents=True)
    (oa / "python" / "bin").mkdir(parents=True)

    shutil.copy2(REPO_ROOT / "linux" / "openaver", app / "linux" / "openaver")
    (app / "linux" / "openaver").chmod(0o755)
    shutil.copy2(REPO_ROOT / "linux" / "prepare_server.py", app / "linux" / "prepare_server.py")
    shutil.copytree(
        REPO_ROOT / "core",
        app / "core",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    shutil.copy2(REPO_ROOT / "web" / "config.default.json", app / "web" / "config.default.json")
    (app / "scripts" / "verify_artifact_imports.py").write_text(
        "# stub verify — not executed by the python stub beyond argv match\n",
        encoding="utf-8",
    )

    py_stub = (
        "#!/bin/bash\n"
        'case "${1:-}" in\n'
        "  *prepare_server.py)\n"
        f"    exec {sys.executable} \"$@\"\n"
        "    ;;\n"
        "  *)\n"
        "    exit 0\n"
        "    ;;\n"
        "esac\n"
    )
    _write_exec(oa / "python" / "bin" / "python3", py_stub)

    with tarfile.open(out, "w:gz") as tar:
        for d in (
            "OpenAver",
            "OpenAver/app",
            "OpenAver/app/linux",
            "OpenAver/app/scripts",
            "OpenAver/app/web",
            "OpenAver/python",
            "OpenAver/python/bin",
        ):
            info = tarfile.TarInfo(d)
            info.type = tarfile.DIRTYPE
            info.mode = 0o755
            tar.addfile(info)

        link = tarfile.TarInfo("OpenAver/openaver")
        link.type = tarfile.SYMTYPE
        link.linkname = "app/linux/openaver"
        tar.addfile(link)

        for rel, mode in (
            ("app/linux/openaver", 0o755),
            ("app/linux/prepare_server.py", 0o644),
            ("app/web/config.default.json", 0o644),
            ("app/scripts/verify_artifact_imports.py", 0o644),
            ("python/bin/python3", 0o755),
        ):
            fp = oa / rel
            ti = tar.gettarinfo(str(fp), arcname=f"OpenAver/{rel}")
            ti.mode = mode
            with fp.open("rb") as fh:
                tar.addfile(ti, fh)

        _add_tree_to_tar(tar, app / "core", "OpenAver/app/core")

    return out


def _install_env(base: Path, fakebin_opts: dict, env_extra: dict[str, str] | None) -> tuple[dict, Path]:
    home = base / "home"
    home.mkdir(parents=True, exist_ok=True)
    opts = dict(fakebin_opts)
    opts["curl_flag"] = base / "curl_called"
    _make_fakebin(base / "fakebin", **opts)
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["OPENAVER_INSTALL_LANG"] = "zh-TW"
    env["PATH"] = f"{base / 'fakebin'}{os.pathsep}{env.get('PATH', '')}"
    # Avoid inheriting a real tarball override from the parent environment.
    for k in ("OPENAVER_TARBALL", "OPENAVER_INSTALL_NO_START", "OPENAVER_YES"):
        env.pop(k, None)
    if env_extra:
        env.update(env_extra)
    return env, home


def _run_install(
    tmp_path: Path,
    *,
    fakebin_opts: dict,
    env_extra: dict[str, str] | None = None,
    args: list[str] | None = None,
    timeout: float = 120,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    env, home = _install_env(tmp_path, fakebin_opts, env_extra)
    proc = subprocess.run(
        ["bash", "-s", "--", *(args or [])],
        input=INSTALL_SH.read_text(encoding="utf-8"),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        start_new_session=True,
        check=False,
    )
    return proc, home


def _combined(proc: subprocess.CompletedProcess[str]) -> str:
    return (proc.stdout or "") + (proc.stderr or "")


@pytest.mark.parametrize(
    "case,fake_opts,needle",
    [
        ("arch", {"arch": "armv7l"}, "armv7l"),
        (
            "musl",
            {
                "ldd_body": "musl libc (x86_64)\n",
                "ldd_rc": 1,
            },
            "musl",
        ),
        ("glibc", {"glibc": "2.9"}, "2.9"),
        ("long_bit", {"long_bit": "32"}, "x86_64"),
    ],
    ids=["arch", "musl", "glibc", "long_bit"],
)
def test_unsupported_machine_stops_before_any_download_or_file(
    tmp_path: Path,
    case: str,
    fake_opts: dict,
    needle: str,
) -> None:
    del case  # parametrize id only
    proc, home = _run_install(tmp_path, fakebin_opts=fake_opts)
    out = _combined(proc)
    assert proc.returncode != 0
    assert needle in out
    leftover = sorted(p for p in home.rglob("*") if p != home)
    assert leftover == [], f"HOME not empty: {leftover}"
    assert not (tmp_path / "curl_called").exists()


def test_fresh_install_places_tree_enables_server_mode_and_links(
    tmp_path: Path,
    stub_tarball: Path,
) -> None:
    proc, home = _run_install(
        tmp_path,
        fakebin_opts={
            "glibc": "2.28",
            "with_autostart_fakes": True,
        },
        env_extra={
            "OPENAVER_TARBALL": str(stub_tarball),
            "OPENAVER_INSTALL_NO_START": "1",
        },
    )
    out = _combined(proc)
    assert proc.returncode == 0, out
    root = home / "OpenAver"
    assert (root / "app").is_dir()
    assert (root / "python").is_dir()
    link = root / "openaver"
    assert link.is_symlink()
    assert link.readlink().as_posix() == "app/linux/openaver"
    local = home / ".local" / "bin" / "openaver"
    assert local.is_symlink()
    assert local.resolve() == link.resolve()

    layout = root / "output" / ".layout.json"
    config = root / "output" / "config.json"
    assert layout.is_file()
    cfg = json.loads(config.read_text(encoding="utf-8"))
    assert cfg["general"]["server_mode"] is True

    assert "沒有終端機" in out
    stages = list(root.glob(".stage-*"))
    assert stages == [], f"stage leftovers: {stages}"
    assert not (tmp_path / "curl_called").exists()


OLD_ITEMS = ("README.md", "requirements.txt", "core", "venv")
KEEP_ITEMS = ("media", "docker-compose.yml", "notes.txt", "logs", "output")


def _manifest(root: Path) -> dict[str, tuple]:
    """path -> (type, mode, sha256 | readlink); lstat only, never follows links."""
    out: dict[str, tuple] = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in dirnames + filenames:
            p = Path(dirpath) / name
            st = p.lstat()
            rel = p.relative_to(root).as_posix()
            if stat.S_ISLNK(st.st_mode):
                out[rel] = ("link", os.readlink(p))
            elif stat.S_ISDIR(st.st_mode):
                out[rel] = ("dir", stat.S_IMODE(st.st_mode))
            else:
                digest = hashlib.sha256(p.read_bytes()).hexdigest()
                out[rel] = ("file", stat.S_IMODE(st.st_mode), digest)
    return out


@pytest.fixture(scope="module")
def output_template(stub_tarball: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """An output/ dir as a post-bootstrap manual install leaves it (server_mode false)."""
    work = tmp_path_factory.mktemp("t5bi-out")
    with tarfile.open(stub_tarball) as tar:
        tar.extractall(work, filter="data")
    out = work / "OpenAver" / "output"
    env = dict(os.environ, OPENAVER_DATA_DIR=str(out))
    prepare = work / "OpenAver" / "app" / "linux" / "prepare_server.py"
    subprocess.run([sys.executable, str(prepare)], env=env, check=True)
    cfg_path = out / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["general"]["server_mode"] = False
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    (out / "library.db").write_bytes(b"not-a-real-db\x00\x01")
    return out


def _build_legacy_home(home: Path, output_template: Path) -> None:
    root = home / "OpenAver"
    root.mkdir(parents=True)
    (root / "README.md").write_text("old readme\n", encoding="utf-8")
    (root / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    (root / "core").mkdir()
    (root / "core" / "x.py").write_text("x = 1\n", encoding="utf-8")
    (root / "venv" / "bin").mkdir(parents=True)
    (root / "venv" / "lib").mkdir()
    (root / "venv" / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")
    (root / "venv" / "bin" / "python3").symlink_to("/usr/bin/python3")
    (root / "venv" / "lib" / "broken").symlink_to("/nonexistent/target")
    (root / "media").mkdir()
    (root / "media" / "movie.mp4").write_bytes(b"\x00fake-video\xff")
    (root / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    (root / "notes.txt").write_text("mine\n", encoding="utf-8")
    (root / "logs").mkdir()
    (root / "logs" / "server.log").write_text("log\n", encoding="utf-8")
    shutil.copytree(output_template, root / "output", symlinks=True)


def _tamper_tar(src: Path, dst: Path, kind: str) -> Path:
    if kind == "truncated":
        data = src.read_bytes()
        dst.write_bytes(data[: len(data) // 2])
        return dst
    with tarfile.open(src) as a, tarfile.open(dst, "w:gz") as b:
        for m in a.getmembers():
            b.addfile(m, a.extractfile(m) if m.isfile() else None)
        extra = tarfile.TarInfo("OpenAver/extra")
        extra.size = 2
        b.addfile(extra, io.BytesIO(b"hi"))
    return dst


@pytest.fixture(scope="module")
def tampered_tars(stub_tarball: Path, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    d = tmp_path_factory.mktemp("t5bi-tars")
    return {k: _tamper_tar(stub_tarball, d / f"{k}.tar.gz", k) for k in ("truncated", "extra_member")}


def _legacy_run(tmp_path: Path, output_template: Path, tarball: str, *, yes: bool, pre=None, **opts):
    home = tmp_path / "home"
    _build_legacy_home(home, output_template)
    if pre is not None:
        pre(home / "OpenAver")
    before = _manifest(home)
    env = {"OPENAVER_TARBALL": tarball, "OPENAVER_INSTALL_NO_START": "1"}
    if yes:
        env["OPENAVER_YES"] = "1"
    fake = {"glibc": "2.28", "with_autostart_fakes": True, "tar_log": tmp_path / "tar_args", **opts}
    proc, _ = _run_install(tmp_path, fakebin_opts=fake, env_extra=env)
    return proc, before, _manifest(home), _combined(proc)


def _make_old_install_dir(root: Path) -> None:
    (root / ".old-install").mkdir()
    (root / ".old-install" / "sentinel.txt").write_text("keep\n", encoding="utf-8")


@pytest.mark.parametrize("old_install_exists", [False, True], ids=["plain", "old_install_exists"])
def test_retrofit_moves_only_known_old_files_and_keeps_user_files_and_data(
    tmp_path: Path, stub_tarball: Path, output_template: Path, old_install_exists: bool
) -> None:
    pre = _make_old_install_dir if old_install_exists else None
    proc, before, after, out = _legacy_run(tmp_path, output_template, str(stub_tarball), yes=True, pre=pre)
    assert proc.returncode == 0, out
    assert "確認沒問題可自行刪除" in out
    root = tmp_path / "home" / "OpenAver"
    assert not (root / "venv").exists() and not (root / "venv").is_symlink()
    assert (root / "app").is_dir() and (root / "python").is_dir() and (root / "openaver").is_symlink()
    assert list(root.glob(".stage-*")) == []
    if old_install_exists:
        dests = sorted(p.name for p in root.glob(".old-install-*"))
        assert len(dests) == 1, dests
        dest = dests[0]
    else:
        dest = ".old-install"
    for rel, entry in before.items():
        if "/" not in rel:
            continue
        top = rel.split("/")[1]
        if top in OLD_ITEMS:
            moved = rel.replace(f"OpenAver/{top}", f"OpenAver/{dest}/{top}", 1)
            assert after.get(moved) == entry, f"old item not moved intact: {rel}"
            assert rel not in after, f"old item still in place: {rel}"
        elif rel != "OpenAver/output/config.json":
            assert after.get(rel) == entry, f"kept item changed: {rel}"
    cfg_before = json.loads((output_template / "config.json").read_text(encoding="utf-8"))
    cfg_after = json.loads((root / "output" / "config.json").read_text(encoding="utf-8"))
    assert cfg_after["general"]["server_mode"] is True
    cfg_after["general"]["server_mode"] = cfg_before["general"]["server_mode"]
    assert cfg_after == cfg_before


@pytest.mark.parametrize(
    "case,needle",
    [
        ("truncated", "壓縮檔內容無效"),
        ("extra_member", "OpenAver/extra"),
        ("extract_fails", "解壓縮失敗"),
        ("download_fails", "下載失敗"),
        ("pre_layout", "0.16 以前的舊安裝"),
    ],
    ids=["truncated", "extra_member", "extract_fails", "download_fails", "pre_layout"],
)
def test_prepare_failure_leaves_tree_untouched(
    tmp_path: Path, stub_tarball: Path, output_template: Path, tampered_tars: dict, case: str, needle: str
) -> None:
    tar_log = tmp_path / "tar_args"
    if case == "download_fails":
        proc, _ = _run_install(
            tmp_path,
            fakebin_opts={"glibc": "2.28", "tar_log": tar_log},
            env_extra={"OPENAVER_TARBALL": "http://127.0.0.1:1/x.tar.gz", "OPENAVER_INSTALL_NO_START": "1"},
        )
        assert proc.returncode != 0
        assert needle in _combined(proc)
        assert (tmp_path / "curl_called").exists()
        assert list((tmp_path / "home").rglob("*")) == []
        return
    tarball = tampered_tars[case] if case in tampered_tars else stub_tarball
    pre = (lambda root: (root / "output" / ".layout.json").unlink()) if case == "pre_layout" else None
    proc, before, after, out = _legacy_run(
        tmp_path, output_template, str(tarball), yes=True, pre=pre, tar_fail_extract=(case == "extract_fails")
    )
    assert proc.returncode != 0, out
    assert needle in out
    assert after == before
    args = tar_log.read_text(encoding="utf-8").split() if tar_log.exists() else []
    assert ("xzf" in args) == (case == "extract_fails")


def test_retrofit_without_confirmation_is_refused_and_tree_unchanged(
    tmp_path: Path, stub_tarball: Path, output_template: Path
) -> None:
    proc, before, after, out = _legacy_run(tmp_path, output_template, str(stub_tarball), yes=False)
    assert proc.returncode != 0, out
    assert "OPENAVER_YES=1" in out
    assert after == before
    assert not (tmp_path / "curl_called").exists()


# ---- T5b-ii: 升級換位（SWAP／COMMIT／ROLLBACK）與 openaver update ----
OLD_VER, NEW_VER = "0.0.1", "0.0.2"
OPTS = {"glibc": "2.28", "with_autostart_fakes": True}
NO_START = {"OPENAVER_INSTALL_NO_START": "1"}


def _variant_tar(src: Path, dst: Path, *, version: str, prepare_fails: bool = False) -> Path:
    with tarfile.open(src) as a, tarfile.open(dst, "w:gz") as b:
        for m in a.getmembers():
            data = a.extractfile(m).read() if m.isfile() else None
            if m.name == "OpenAver/app/core/version.py":
                data = re.sub(rb'(?m)^__version__ = "[^"]*"', f'__version__ = "{version}"'.encode(), data)
            elif m.name == "OpenAver/python/bin/python3":
                if prepare_fails:
                    data = b'#!/bin/bash\ncase "${1:-}" in\n  *prepare_server.py) exit 1 ;;\n  *) exit 0 ;;\nesac\n'
                data += f"# variant {version}\n".encode()
            if data is None:
                b.addfile(m)
            else:
                m.size = len(data)
                b.addfile(m, io.BytesIO(data))
    return dst


@pytest.fixture(scope="module")
def upgrade_tars(stub_tarball: Path, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    d = tmp_path_factory.mktemp("t5bii-tars")
    new = _variant_tar(stub_tarball, d / "new.tar.gz", version=NEW_VER)
    return {
        "old": _variant_tar(stub_tarball, d / "old.tar.gz", version=OLD_VER),
        "new": new,
        "bad": _variant_tar(stub_tarball, d / "bad.tar.gz", version=NEW_VER, prepare_fails=True),
        "truncated": _tamper_tar(new, d / "truncated.tar.gz", "truncated"),
    }


def _install_old(base: Path, old_tar: Path) -> Path:
    """Fresh-install the old version, then add data and user files that must never change."""
    proc, home = _run_install(base, fakebin_opts=OPTS, env_extra={"OPENAVER_TARBALL": str(old_tar), **NO_START})
    assert proc.returncode == 0, _combined(proc)
    root = home / "OpenAver"
    (root / "output" / "covers").mkdir(parents=True, exist_ok=True)
    (root / "output" / "library.db").write_bytes(b"SQLite format 3\x00\xde\xad\xbe\xef")
    (root / "output" / "_sentinel.txt").write_text("keep\n", encoding="utf-8")
    (root / "output" / "covers" / "x.jpg").write_bytes(b"\xff\xd8jpeg")
    (root / "media").mkdir()
    (root / "media" / "movie.mp4").write_bytes(b"\x00fake-video\xff")
    (root / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    return home


def _run_update(base: Path, tarball: Path) -> subprocess.CompletedProcess[str]:
    env, home = _install_env(base, {**OPTS, "curl_serves": INSTALL_SH}, {"OPENAVER_TARBALL": str(tarball), **NO_START})
    return subprocess.run(
        [str(home / "OpenAver" / "openaver"), "update"],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        start_new_session=True,
        check=False,
    )


def _status(home: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, HOME=str(home), OPENAVER_INSTALL_LANG="zh-TW")
    return subprocess.run([str(home / "OpenAver" / "openaver"), "status"], env=env, capture_output=True, text=True)


def _top(rel: str) -> str:
    parts = rel.split("/")
    return parts[1] if parts[0] == "OpenAver" and len(parts) > 1 else ""


def _prune(m: dict, drop: tuple[str, ...]) -> dict:
    return {k: v for k, v in m.items() if not _top(k).startswith(drop)}


def _subtree(m: dict, prefix: str) -> dict:
    return {k[len(prefix):]: v for k, v in m.items() if k == prefix or k.startswith(prefix + "/")}


@contextlib.contextmanager
def _fake_service(cwd: Path, pidfile: Path | None = None):
    """A uvicorn-looking process that is adopted by init, so a kill really makes it vanish."""
    script = 'cd "$1" && exec -a "uvicorn web.app:app" sleep 300 </dev/null >/dev/null 2>&1 & echo $!'
    out = subprocess.run(["bash", "-c", script, "_", str(cwd)], capture_output=True, text=True, timeout=10, check=True)
    pid = int(out.stdout.strip())
    try:
        if pidfile is not None:
            pidfile.parent.mkdir(parents=True, exist_ok=True)
            pidfile.write_text(f"{pid}\n", encoding="utf-8")
        yield pid
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _spawn_swap(base: Path, tarball: Path, *, kill_at: int | None, sig: str = "") -> tuple[subprocess.Popen, str, list[str]]:
    mv_log, count = base / "mv.log", base / "mv.count"
    for f in (mv_log, count):
        f.unlink(missing_ok=True)
    extra = {"OPENAVER_TARBALL": str(tarball), "MV_COUNT_FILE": str(count), **NO_START}
    if kill_at is not None:
        extra["MV_KILL_AT"] = str(kill_at)
        if sig:
            extra["MV_SIGNAL"] = sig
    env, _ = _install_env(base, {**OPTS, "mv_log": mv_log}, extra)
    proc = subprocess.Popen(
        ["bash", "-s", "--"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env=env, text=True, start_new_session=True,
    )
    out, err = proc.communicate(INSTALL_SH.read_text(encoding="utf-8"), timeout=120)
    return proc, out + err, (mv_log.read_text().splitlines() if mv_log.exists() else [])


@pytest.mark.parametrize("case", ["truncated_while_service_runs", "prepare_fails_after_swap", "retrofit_prepare_fails"])
def test_failed_upgrade_restores_previous_install(
    tmp_path: Path, upgrade_tars: dict, output_template: Path, case: str
) -> None:
    if case == "retrofit_prepare_fails":
        proc, before, after, out = _legacy_run(tmp_path, output_template, str(upgrade_tars["bad"]), yes=True)
        assert proc.returncode != 0 and "已還原" in out, out
        assert after == before
        return
    home = _install_old(tmp_path, upgrade_tars["old"])
    root = home / "OpenAver"
    running = case == "truncated_while_service_runs"
    with _fake_service(root / "app", root / "run" / "openaver.pid") if running else contextlib.nullcontext(0) as pid:
        before = _manifest(home)
        proc = _run_update(tmp_path, upgrade_tars["truncated" if running else "bad"])
        out = _combined(proc)
        assert proc.returncode != 0, out
        assert ("壓縮檔內容無效" if running else "已還原") in out
        assert _alive(pid) or not running, out
        skip = () if running else ("logs", "run")
        assert _prune(_manifest(home), skip) == _prune(before, skip)
        assert not list(root.glob(".prev*")) and not list(root.glob(".stage-*"))
        st = _status(home)
        assert OLD_VER in st.stdout and st.returncode == (0 if running else 3)


def test_upgrade_never_touches_data_or_user_files(tmp_path: Path, upgrade_tars: dict) -> None:
    home = _install_old(tmp_path, upgrade_tars["old"])
    root = home / "OpenAver"
    before = _manifest(home)
    cfg_before = json.loads((root / "output" / "config.json").read_text(encoding="utf-8"))
    proc = _run_update(tmp_path, upgrade_tars["new"])
    assert proc.returncode == 0, _combined(proc)
    assert not (tmp_path / "curl_called").exists()
    after = _manifest(home)
    for rel, entry in before.items():
        if _top(rel) in ("output", "media", "docker-compose.yml") and rel != "OpenAver/output/config.json":
            assert after.get(rel) == entry, rel
    cfg_after = json.loads((root / "output" / "config.json").read_text(encoding="utf-8"))
    cfg_after["general"]["server_mode"] = cfg_before["general"]["server_mode"]
    assert cfg_after == cfg_before
    assert NEW_VER in (root / "app" / "core" / "version.py").read_text(encoding="utf-8")
    assert NEW_VER in (root / "python" / "bin" / "python3").read_text(encoding="utf-8")
    assert (root / "openaver").is_symlink() and not list(root.glob(".prev*"))
    st = _status(home)
    assert st.returncode == 3 and NEW_VER in st.stdout


@pytest.mark.parametrize("k", range(1, 7), ids=[f"k{i}" for i in range(1, 7)])
def test_rerun_after_killed_swap_renames_leftovers_and_deletes_nothing(tmp_path: Path, upgrade_tars: dict, k: int) -> None:
    new = upgrade_tars["new"]
    _install_old(tmp_path / "base", upgrade_tars["old"])
    proc, out, mvs = _spawn_swap(tmp_path / "base", new, kill_at=None)
    assert len(mvs) == 6, (mvs, out)
    assert {ln.split("\t")[0] for ln in mvs} == {str(proc.pid)}, mvs
    assert proc.returncode == 0, out

    home = _install_old(tmp_path, upgrade_tars["old"])
    proc, out, _ = _spawn_swap(tmp_path, new, kill_at=k)
    assert proc.returncode == -9, out
    killed = _manifest(home)
    stages = {r.split("/")[1] for r in killed if r.startswith("OpenAver/.stage-")}
    assert len(stages) == 1 and "OpenAver/.prev" in killed

    proc, _ = _run_install(tmp_path, fakebin_opts=OPTS, env_extra={"OPENAVER_TARBALL": str(upgrade_tars["truncated"]), **NO_START})
    assert proc.returncode != 0 and "壓縮檔內容無效" in _combined(proc)
    assert _manifest(home) == killed

    proc, _ = _run_install(tmp_path, fakebin_opts=OPTS, env_extra={"OPENAVER_TARBALL": str(new), **NO_START})
    assert proc.returncode == 0, _combined(proc)
    root, final = home / "OpenAver", _manifest(home)
    assert NEW_VER in (root / "app" / "core" / "version.py").read_text(encoding="utf-8")
    assert NEW_VER in (root / "python" / "bin" / "python3").read_text(encoding="utf-8")
    assert (root / "openaver").is_symlink() and (root / "openaver").resolve().is_file()
    prevs = sorted(p.name for p in root.glob(".prev-*"))
    assert len(prevs) == 1 and not (root / ".prev").exists(), prevs
    assert _subtree(final, f"OpenAver/{prevs[0]}") == _subtree(killed, "OpenAver/.prev")
    (stage,) = stages
    assert _subtree(final, f"OpenAver/{stage}") == _subtree(killed, f"OpenAver/{stage}")
    drop = ("app", "python", "openaver", "run", "logs", ".prev", ".stage")
    assert _prune(final, drop) == _prune(killed, drop)


@pytest.mark.parametrize("case", ["ours_pidfile", "foreign"])
def test_managed_service_is_stopped_for_upgrade_but_foreign_one_blocks(tmp_path: Path, upgrade_tars: dict, case: str) -> None:
    home = _install_old(tmp_path, upgrade_tars["old"])
    root = home / "OpenAver"
    ours = case == "ours_pidfile"
    with _fake_service(root / "app" if ours else root, root / "run" / "openaver.pid" if ours else None) as pid:
        before = _manifest(home)
        proc = _run_update(tmp_path, upgrade_tars["new"])
        out = _combined(proc)
        if ours:
            assert proc.returncode == 0, out
            assert not _alive(pid) and NEW_VER in (root / "app" / "core" / "version.py").read_text(encoding="utf-8")
        else:
            assert proc.returncode != 0 and "舊的 OpenAver 服務還在執行" in out
            assert _alive(pid) and _manifest(home) == before


@pytest.mark.parametrize("k", [5, 6], ids=["k5", "k6"])
def test_rerun_without_tarball_after_half_placed_swap_is_not_called_latest(tmp_path: Path, upgrade_tars: dict, k: int) -> None:
    new = upgrade_tars["new"]
    home = _install_old(tmp_path, upgrade_tars["old"])
    proc, out, _ = _spawn_swap(tmp_path, new, kill_at=k)
    assert proc.returncode == -9, out
    root = home / "OpenAver"
    assert NEW_VER in (root / "app" / "core" / "version.py").read_text(encoding="utf-8")
    assert not (root / "openaver").exists()
    proc, _ = _run_install(tmp_path, fakebin_opts={**OPTS, "curl_release": (NEW_VER, new)}, env_extra=NO_START)
    out = _combined(proc)
    assert "已是最新" not in out and proc.returncode == 0, out
    assert NEW_VER in (root / "python" / "bin" / "python3").read_text(encoding="utf-8")
    assert (root / "openaver").resolve().is_file() and len(list(root.glob(".prev-*"))) == 1


def test_interrupt_signal_during_swap_is_ignored_and_swap_completes(tmp_path: Path, upgrade_tars: dict) -> None:
    home = _install_old(tmp_path, upgrade_tars["old"])
    proc, out, mvs = _spawn_swap(tmp_path, upgrade_tars["new"], kill_at=3, sig="INT")
    root = home / "OpenAver"
    assert proc.returncode == 0 and "請勿中斷" in out and len(mvs) == 6, (proc.returncode, out, mvs)
    for item in ("app", "python"):
        assert NEW_VER in next((root / item).rglob("version.py" if item == "app" else "python3")).read_text(encoding="utf-8")
    assert (root / "openaver").resolve().is_file() and not list(root.glob(".prev*"))
