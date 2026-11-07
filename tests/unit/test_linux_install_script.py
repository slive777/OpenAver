"""TASK-194-T5a: install.sh Linux 分支（偵測擋下／全新安裝就位）。"""

from __future__ import annotations

import json
import os
import shutil
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
    curl_flag: Path,
    with_autostart_fakes: bool = False,
) -> None:
    fakebin.mkdir(parents=True, exist_ok=True)
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
        "exit 1\n",
    )
    _write_exec(
        fakebin / "curl",
        "#!/bin/bash\n"
        f': > "{curl_flag}"\n'
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


def _run_install(
    tmp_path: Path,
    *,
    fakebin_opts: dict,
    env_extra: dict[str, str] | None = None,
    args: list[str] | None = None,
    timeout: float = 120,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    fakebin = tmp_path / "fakebin"
    curl_flag = tmp_path / "curl_called"
    opts = dict(fakebin_opts)
    opts["curl_flag"] = curl_flag
    _make_fakebin(fakebin, **opts)

    env = dict(os.environ)
    env["HOME"] = str(home)
    env["OPENAVER_INSTALL_LANG"] = "zh-TW"
    env["PATH"] = f"{fakebin}{os.pathsep}{env.get('PATH', '')}"
    # Avoid inheriting a real tarball override from the parent environment.
    env.pop("OPENAVER_TARBALL", None)
    env.pop("OPENAVER_INSTALL_NO_START", None)
    env.pop("OPENAVER_YES", None)
    if env_extra:
        env.update(env_extra)

    text = INSTALL_SH.read_text(encoding="utf-8")
    proc = subprocess.run(
        ["bash", "-s", "--", *(args or [])],
        input=text,
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
    ],
    ids=["arch", "musl", "glibc"],
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
