"""186-T4b：掃描收尾的圖片相似增量接點不得拖垮掃描完成事件。"""
import json

import pytest

pytestmark = pytest.mark.usefixtures("isolate_reconcile_db")


def test_scan_done_survives_incremental_failure(tmp_path, monkeypatch, mocker):
    """R1：端點或索引排程出錯 → 使用者的掃描卡住不結束。"""
    from core.gallery_scanner import VideoInfo
    from core.path_utils import to_file_uri
    from web.routers.scanner import generate_avlist

    src = tmp_path / "src"
    src.mkdir()
    (src / "v.mp4").write_bytes(b"x" * 2048)
    out = tmp_path / "html_out"
    out.mkdir()
    cfg = {
        "gallery": {"directories": [str(src)], "output_dir": str(out),
                    "path_mappings": {}, "min_size_mb": 0},
        "search": {"proxy_url": ""}, "general": {"theme": "light"},
        "scraper": {"video_extensions": [".mp4"]},
    }
    monkeypatch.setattr("web.routers.scanner.load_config", lambda: cfg)
    monkeypatch.setattr("web.routers.scanner.get_db_path", lambda: tmp_path / "test.db")
    mocker.patch(
        "web.routers.scanner.VideoScanner.scan_file",
        lambda self, p, base_path=None: VideoInfo(path=to_file_uri(p), title="t", num="ABC-001"),
    )
    mocker.patch("web.routers.scanner.HTMLGenerator")
    mocker.patch("web.routers.scanner._emit_notif")
    hook = mocker.patch(
        "web.routers.scanner.similar_index.schedule_incremental",
        side_effect=RuntimeError("boom"),
    )

    chunks = list(generate_avlist())

    events = [json.loads(line[6:]) for c in chunks for line in c.split("\n") if line.startswith("data: ")]
    assert [e for e in events if e.get("type") == "done"], f"done 事件缺席：{events}"
    assert hook.call_count == 1
