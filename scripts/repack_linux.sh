#!/bin/bash
# scripts/repack_linux.sh — 由 Synology SPK 的位元組重新包裝成 Linux tar.gz（不另跑 pip）
#
# 用法：bash scripts/repack_linux.sh <spk> <out-dir> [arch...]
#   arch 預設 "x86_64 aarch64"；本機重包可只傳 x86_64
# 產物：<out-dir>/OpenAver-v<APPVER>-Linux-<arch>.tar.gz
#   OpenAver/app/、OpenAver/python/（由 python-<arch> 改名）、OpenAver/openaver -> app/linux/openaver
# APPVER 取自 SPK 內 app/core/version.py。連結目標存不存在由 audit 的 LAYOUT 把關，這裡不驗。
# fail-closed：SPK 打不開／缺 package.tgz／缺 app／缺要求的 python-<arch>／讀不到版本
# → 非零退出，out-dir 不留半成品（成品最後才 mv 進去）。
set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo "usage: $0 <spk> <out-dir> [arch...]" >&2
  exit 2
fi
SPK="$1"; OUT="$2"; shift 2
if [ "$#" -gt 0 ]; then ARCHS=("$@"); else ARCHS=(x86_64 aarch64); fi

[ -f "$SPK" ] || { echo "repack: SPK not found: $SPK" >&2; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

tar xf "$SPK" -C "$WORK" package.tgz 2>/dev/null \
  || { echo "repack: cannot read package.tgz from $SPK" >&2; exit 1; }

tar tzf "$WORK/package.tgz" > "$WORK/members"
grep -q '^app/' "$WORK/members" || { echo "repack: package.tgz has no app/" >&2; exit 1; }
for A in "${ARCHS[@]}"; do
  grep -q "^python-$A/" "$WORK/members" \
    || { echo "repack: package.tgz has no python-$A/ (requested arch missing)" >&2; exit 1; }
done

PKG="$WORK/pkg"; mkdir -p "$PKG"
tar xzf "$WORK/package.tgz" -C "$PKG" app $(printf 'python-%s ' "${ARCHS[@]}")

APPVER=$(grep -oP '__version__ = "\K[^"]+' "$PKG/app/core/version.py" || true)
[ -n "$APPVER" ] || { echo "repack: cannot read version from app/core/version.py" >&2; exit 1; }
echo "[repack] app version $APPVER"

mkdir -p "$OUT"
DONE="$WORK/done"; mkdir -p "$DONE"
for A in "${ARCHS[@]}"; do
  STAGE="$WORK/stage-$A"; mkdir -p "$STAGE/OpenAver"
  cp -a "$PKG/app" "$STAGE/OpenAver/app"
  cp -a "$PKG/python-$A" "$STAGE/OpenAver/python"
  ln -s app/linux/openaver "$STAGE/OpenAver/openaver"
  TAR="OpenAver-v$APPVER-Linux-$A.tar.gz"
  tar czf "$DONE/$TAR" --owner=0 --group=0 --numeric-owner -C "$STAGE" OpenAver
  rm -rf "$STAGE"
  echo "[repack] built $TAR"
done

mv "$DONE"/*.tar.gz "$OUT"/
ls -la "$OUT"
