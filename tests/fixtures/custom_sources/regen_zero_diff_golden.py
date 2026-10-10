"""重產 zero_diff_golden.json（純腳本，不被 pytest 收集、不連外）。

基準＝commit 35a9cb70（165 之前）的乾淨樹。步驟：
  git clone --local /home/peace/OpenAver "$HOME/.cache/openaver-golden-35a9cb70"   # 必須在 $HOME 下，不是 /tmp
  git -C "$HOME/.cache/openaver-golden-35a9cb70" checkout 35a9cb70
  cd "$HOME/.cache/openaver-golden-35a9cb70"
  PYTHONPATH=$PWD <本 repo>/venv/bin/python <本 repo>/tests/fixtures/custom_sources/regen_zero_diff_golden.py <輸出 json 路徑>
`capture(client)` 的本文與 tests/integration/test_custom_source_zero_diff.py 的 `_capture` 逐字相同。
"""
import json
import os
import sys
import tempfile
from pathlib import Path

BASELINE_COMMIT = "35a9cb70"


def capture(client):
    out = {}
    root = os.environ["OPENAVER_DATA_DIR"]

    def raw(url):  # resp.text 原文；唯一的替換是把 tmp 資料根換成佔位符（golden 不得含絕對路徑）
        return client.get(url).text.replace(root, "<DATA_ROOT>")

    out["search_sources"] = raw("/api/search/sources")
    out["scraper_sources"] = raw("/api/scraper-sources")
    out["config_sources"] = raw("/api/config")
    enums = {}

    def walk(node, tool, trail):
        if isinstance(node, dict):
            if "path" in node and "method" in node and isinstance(node["path"], str):
                tool = f'{node["method"]} {node["path"]}'
                trail = ""
            for key, val in node.items():
                if key == "source" and isinstance(val, dict) and isinstance(val.get("enum"), list) and tool:
                    if "custom-sources" not in tool:
                        enums[f"{tool} {trail}"] = val["enum"]
                walk(val, tool, f"{trail}/{key}")
        elif isinstance(node, list):
            for i, val in enumerate(node):
                walk(val, tool, f"{trail}/{i}")

    walk(client.get("/api/capabilities").json(), "", "")
    out["capabilities_source_enums"] = dict(sorted(enums.items()))
    return out


def main():
    dest = Path(sys.argv[1]).resolve()
    root = Path(tempfile.mkdtemp(prefix="oa-golden-")) / "root"
    root.mkdir()
    os.environ["OPENAVER_DATA_DIR"] = str(root)
    (root / ".layout.json").write_text(json.dumps({"version": 1, "complete": True}), encoding="utf-8")
    import starlette.testclient as stc
    orig = stc.TestClient.__init__

    def _init(self, *a, **kw):
        kw.setdefault("client", ("127.0.0.1", 50000))
        orig(self, *a, **kw)

    stc.TestClient.__init__ = _init
    from core import config as core_config
    cfg_dir = root.parent / "config"
    cfg_dir.mkdir()
    core_config.CONFIG_PATH = cfg_dir / "test_config.json"
    core_config.CONFIG_DEFAULT_PATH = cfg_dir / "test_config.default.json"
    core_config.CONFIG_PATH.write_text(json.dumps(core_config.AppConfig().model_dump()), encoding="utf-8")
    from core.database import init_db
    import core.access_auth as access_auth
    import core.database.connection as db_conn
    import core.wishlist_cover_cache as wcc
    db_path = root.parent / "isolate.db"
    init_db(db_path)
    db_conn.get_db_path = lambda: db_path
    wcc.get_db_path = lambda: db_path
    access_auth.get_db_path = lambda: root.parent / "access_auth.db"
    access_auth.reset_state_for_tests()
    access_auth.ensure_schema()
    import web
    import core
    print("core loaded from", core.__file__, file=sys.stderr)
    from fastapi.testclient import TestClient
    from web.app import app
    core_config.save_config(core_config.load_config())
    core_config.save_config(core_config.load_config())
    result = {"baseline_commit": BASELINE_COMMIT}
    result.update(capture(TestClient(app)))
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
