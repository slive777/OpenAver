import pytest

import build_macos


@pytest.mark.parametrize(
    ("contents", "expected"),
    [
        pytest.param([b"\xca\xfe\xba\xbe\x00\x00\x00\x02" + b"\x00" * 8,
                      b"\xcf\xfa\xed\xfe\x0c\x00\x00\x01" + b"\x00" * 8], True, id="macho"),
        pytest.param([b"\x7fELF" + b"\x00" * 8, b"#!/bin/sh\n", b""], False, id="not_macho"),
    ],
)
def test_is_macho_file_by_magic(tmp_path, contents, expected):
    for index, data in enumerate(contents):
        path = tmp_path / str(index)
        path.write_bytes(data)
        assert build_macos.is_macho_file(path) is expected
