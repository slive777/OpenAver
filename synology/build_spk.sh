#!/bin/bash
# synology/build_spk.sh — Synology SPK 打包腳本（搬自 147 草稿）
# build 號＝github.run_number（不疊加 run_attempt）；要產新的、會拿去安裝或發布的 spk 一律開一個新的 workflow run；Re-run 產出的 spk 不得拿去安裝或發布。
#
# 用法：./synology/build_spk.sh <spk-version> <git-ref> "<archs>"
#   例：./synology/build_spk.sh 0.16.6-0001 HEAD "aarch64"
#       ./synology/build_spk.sh 0.16.6-0001 HEAD "aarch64 x86_64"   # 胖包
#
# 前提：synology/cache/python-<arch>-base/ ＝ python-build-standalone 3.12.14 install_only_stripped（site-packages 只剩 pip）
# 產物：synology/out/OpenAver-<spk-version>-<archtag>.spk
set -euo pipefail

VER="$1"; REF="$2"; ARCHS="${3:-aarch64}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
CACHE="$HERE/cache"
OUT="$HERE/out"
WORK="$(mktemp -d "$HERE/work.XXXX")"
trap 'rm -rf "$WORK"' EXIT
PYTHON_BIN="${PYTHON_BIN:-python3}"
PIP_BIN="${PIP_BIN:-pip}"

PKG="$WORK/pkg"; mkdir -p "$PKG" "$OUT"

# ---- app/ ----
mkdir -p "$PKG/app"
git -C "$REPO" archive "$REF" | tar x -C "$PKG/app"
( cd "$PKG/app" && rm -rf docs tests .github node_modules CHANGELOG_ARCHIVE.md windows output && find . -name __pycache__ -prune -exec rm -rf {} + )
APPVER=$(grep -oP '__version__ = "\K[^"]+' "$PKG/app/core/version.py")
echo "[build] app version $APPVER from $REF"

# ---- python-<arch>/ ：兩個架構同一次 resolve（K9-3）----
grep -v '^pywebview' "$PKG/app/requirements.txt" > "$WORK/req-nas.txt"
CONSTRAINT=""
for A in $ARCHS; do
  case "$A" in
    aarch64) PLAT=(--platform manylinux2014_aarch64 --platform manylinux_2_27_aarch64 --platform manylinux_2_28_aarch64 --platform manylinux_2_34_aarch64) ;;
    x86_64)  PLAT=(--platform manylinux2014_x86_64 --platform manylinux_2_27_x86_64 --platform manylinux_2_28_x86_64 --platform manylinux_2_34_x86_64) ;;
    *) echo "unknown arch $A"; exit 1 ;;
  esac
  cp -a "$CACHE/python-$A-base" "$PKG/python-$A"
  SP="$PKG/python-$A/lib/python3.12/site-packages"
  "$PIP_BIN" install -q --no-compile --target "$SP" --upgrade \
     --only-binary=:all: --python-version 3.12 --implementation cp --abi cp312 "${PLAT[@]}" \
     -r "$WORK/req-nas.txt" ${CONSTRAINT:+-c "$CONSTRAINT"}
  if [ -z "$CONSTRAINT" ]; then
    CONSTRAINT="$WORK/constraints.txt"
    ls "$SP" | grep -oP '^.+(?=\.dist-info$)' | grep -v '^pip-' \
      | sed -E 's/^(.+)-([^-]+)$/\1==\2/' > "$CONSTRAINT"
    echo "[build] resolved $(wc -l < "$CONSTRAINT") dists on $A"
  fi
  find "$PKG/python-$A" -name __pycache__ -prune -exec rm -rf {} +
done

( cd "$PKG" && tar czf "$WORK/package.tgz" app python-* )

# ---- 控制成員 ----
S="$WORK/spk"; mkdir -p "$S"
cp -a "$HERE/spk-src/scripts" "$HERE/spk-src/conf" "$HERE/spk-src/WIZARD_UIFILES" "$S/"
chmod 755 "$S"/scripts/* "$S"/WIZARD_UIFILES/*
cp "$REPO/web/static/favicon.png" "$S/PACKAGE_ICON.PNG"
"$PYTHON_BIN" -c "from PIL import Image; Image.open('$REPO/web/static/apple-touch-icon.png').resize((256,256)).save('$S/PACKAGE_ICON_256.PNG')"
sed "s/@VERSION@/$VER/" "$HERE/spk-src/INFO.in" > "$S/INFO"
mv "$WORK/package.tgz" "$S/package.tgz"

TAG=$([ "$(echo $ARCHS | wc -w)" -gt 1 ] && echo fat || echo "$ARCHS")
SPK="$OUT/OpenAver-$VER-$TAG.spk"
tar cf "$SPK" -C "$S" INFO PACKAGE_ICON.PNG PACKAGE_ICON_256.PNG package.tgz scripts conf WIZARD_UIFILES
ls -la "$SPK"
