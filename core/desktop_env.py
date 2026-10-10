"""桌面版種類判斷（TASK-163b-T7a / CD-163b-18）。

`desktop_kind()` 是全站唯一回答「現在是哪種桌面 App」的地方。
呼叫當下才讀 `OPENAVER_STANDALONE` 與 `sys.platform`（不在 import 時存成常數），
測試才能用 monkeypatch 切換。

只有 'windows' 代表驗證視窗是 WebView2（吃 Proxy 欄）；macOS 走同一個
windows/standalone.py 並註冊 transport，所以「transport 是否註冊」不能拿來判平台。
"""
from __future__ import annotations

import os
import sys
from typing import Literal, Optional

DesktopKind = Literal['windows', 'mac']


def desktop_kind() -> Optional[DesktopKind]:
    if os.environ.get('OPENAVER_STANDALONE') != '1':
        return None
    if sys.platform == 'win32':
        return 'windows'
    if sys.platform == 'darwin':
        return 'mac'
    return None
