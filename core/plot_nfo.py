"""plot_nfo — single owner for 'is there a non-empty <plot>?' (CD-187b-4).

All callers that decide True/False for a plot must go through plot_present /
read_plot_flag; do not re-implement .strip() locally.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Union

from core.nfo_read import nfo_text
from core.nfo_utils import sanitize_nfo_bytes


def plot_present(text: Optional[str]) -> bool:
    """True iff text is non-None and has non-whitespace content."""
    return bool(text and text.strip())


def read_plot_flag(nfo_path: Union[str, Path]) -> Optional[bool]:
    """Read whether an on-disk NFO has a non-empty <plot>.

    - file missing → False (confirmed absent)
    - OSError while reading → None (unknown; caller must not collapse to False)
    - sanitize then XML parse failure → False (confirmed unreadable / no plot)
    - otherwise → plot_present(nfo_text(root, 'plot'))
    """
    path = Path(nfo_path)
    if not path.exists():
        return False
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    try:
        raw = sanitize_nfo_bytes(raw)
        root = ET.fromstring(raw)
    except Exception:
        return False
    return plot_present(nfo_text(root, "plot"))
