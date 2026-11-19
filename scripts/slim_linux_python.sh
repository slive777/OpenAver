#!/bin/bash
# Usage: slim_linux_python.sh <python-dir> <strip-tool>
set -euo pipefail

PY="${1:?slim: missing python directory}"
STRIP="${2:?slim: missing strip tool}"
SP="$PY/lib/python3.12/site-packages"
if [ ! -d "$PY" ] || [ ! -f "$PY/bin/python3.12" ]; then
  echo "slim: invalid python directory: $PY" >&2
  exit 2
fi
if ! command -v "$STRIP" >/dev/null; then
  echo "slim: strip tool not found: $STRIP" >&2
  exit 1
fi
find "$PY/lib" -type f \( -name '*.so' -o -name '*.so.*' \) -print0 | xargs -0 -r -n 32 "$STRIP" --strip-unneeded
rm -f "$PY"/lib/libpython3*.so*
rm -rf "$PY"/lib/libtcl* "$PY"/lib/tcl9* "$PY"/lib/tk9* "$PY"/lib/itcl* "$PY"/lib/thread*
rm -rf "$PY/lib/python3.12/tkinter" "$PY"/lib/python3.12/lib-dynload/_tkinter.*
rm -rf "$PY/lib/python3.12/ensurepip" "$PY/lib/python3.12/idlelib"
rm -rf "$SP/pip"
rm -rf "$PY/include" "$PY/share/terminfo"
rm -f "$PY/bin/pip" "$PY/bin/pip3" "$PY/bin/pip3.12" "$PY/bin/idle3" "$PY/bin/idle3.12"
