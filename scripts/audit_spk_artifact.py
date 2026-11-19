"""Audit both bundled Python architectures in a Synology SPK.

Usage: python scripts/audit_spk_artifact.py <spk-glob> [--strict]
Exit 0 when the package passes, 1 otherwise.
"""

from __future__ import annotations

import argparse
import glob
import sys
import tarfile
from pathlib import Path

from audit_build_artifact import RICH_GROUP_TOP_DIRS, rich_group_dist_info_dirs


ARCHS = ("aarch64", "x86_64")
MIN_DIST_INFO_RATIO = 0.5


def audit(spk_path: str | Path, strict: bool = False) -> tuple[int, list[str]]:
    """Return an exit code and findings; all checks hard-fail regardless of strict."""
    path = Path(spk_path)
    messages: list[str] = []
    try:
        with tarfile.open(path, "r:*") as spk:
            member = spk.extractfile("package.tgz")
            if member is None:
                raise ValueError("package.tgz is missing")
            with member, tarfile.open(fileobj=member, mode="r|gz") as package:
                members = {item.name.removeprefix("./").rstrip("/"): item for item in package}
    except (OSError, tarfile.TarError, ValueError, KeyError) as exc:
        return 1, [f"[FAIL] Invalid SPK {path.name}: {exc}"]

    missing: list[str] = []
    counts: dict[str, int] = {}
    for arch in ARCHS:
        prefix = f"python-{arch}/"
        binary = members.get(f"{prefix}bin/python3")
        executable = members.get(f"{prefix}bin/python3.12")
        if (
            binary is None
            or not (binary.isfile() or binary.issym())
            or executable is None
            or not executable.isfile()
        ):
            missing.append(arch)
        site_prefix = f"{prefix}lib/python3.12/site-packages/"
        top_names = {
            name[len(site_prefix):].split("/", 1)[0]
            for name in members
            if name.startswith(site_prefix) and len(name[len(site_prefix):].split("/", 1)[0]) > 0
        }
        leftovers = sorted(RICH_GROUP_TOP_DIRS & top_names) + rich_group_dist_info_dirs(top_names)
        for leftover in leftovers:
            messages.append(f"[FAIL] {arch}: leftover rich-group '{leftover}' in site-packages")
        counts[arch] = len({
            name[len(site_prefix):].split("/", 1)[0]
            for name in members
            if name.startswith(site_prefix)
            and name[len(site_prefix):].split("/", 1)[0].endswith(".dist-info")
        })
        if counts[arch] == 0 and arch not in missing:
            messages.append(f"[FAIL] {arch}: site-packages has no dist-info directories")

    if missing:
        messages.append(f"[FAIL] Missing Python interpreter for: {', '.join(missing)}")
    if all(counts.values()):
        ratio = min(counts.values()) / max(counts.values())
        if ratio < MIN_DIST_INFO_RATIO:
            messages.append(
                f"[FAIL] site-packages dist-info count differs too much: "
                f"aarch64={counts['aarch64']}, x86_64={counts['x86_64']} "
                f"(ratio {ratio:.2f} < {MIN_DIST_INFO_RATIO:.2f})"
            )

    if messages:
        return 1, messages
    return 0, [
        f"[OK] {path.name}: both interpreters present; "
        f"dist-info counts aarch64={counts['aarch64']}, x86_64={counts['x86_64']}"
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spk_glob", help="Glob matching exactly one SPK")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Compatibility with audit_build_artifact.py; all checks already hard-fail",
    )
    args = parser.parse_args(argv)
    matches = glob.glob(args.spk_glob)
    if len(matches) != 1:
        print(f"[FAIL] Expected exactly one SPK, got {len(matches)}: {args.spk_glob}")
        return 1
    code, messages = audit(matches[0], args.strict)
    for message in messages:
        print(message)
    return code


if __name__ == "__main__":
    sys.exit(main())
