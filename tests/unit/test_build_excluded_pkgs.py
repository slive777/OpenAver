"""Windows rich-group filename filter (TASK-203-T1).

Covers build._is_rich_group_pkg: the four rich-group distributions
(rich / pygments / markdown_it_py / mdurl, incl. the capitalised
Pygments sdist) are dropped, while lookalikes (markdown, rich_toolkit)
and unrelated runtime deps are kept.
"""

from __future__ import annotations

import pytest

import build


@pytest.mark.parametrize("case", ["dropped", "kept"])
def test_rich_group_filename_filter(case):
    """dropped: rich-group wheels + capitalised Pygments sdist -> True.

    kept: unrelated runtime deps + lookalikes (markdown, rich_toolkit) -> False.
    """
    if case == "dropped":
        filenames = [
            "rich-14.0.0-py3-none-any.whl",
            "pygments-2.19.2-py3-none-any.whl",
            "markdown_it_py-4.0.0-py3-none-any.whl",
            "mdurl-0.1.2-py3-none-any.whl",
            "Pygments-2.17.2.tar.gz",
        ]
        assert all(build._is_rich_group_pkg(name) for name in filenames)
    else:
        filenames = [
            "curl_cffi-0.13-cp312-cp312-win_amd64.whl",
            "click-8.1.7-py3-none-any.whl",
            "markdown-3.7-py3-none-any.whl",
            "rich_toolkit-0.14.0-py3-none-any.whl",
        ]
        assert not any(build._is_rich_group_pkg(name) for name in filenames)
