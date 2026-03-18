"""
確保專案 Python 模組不使用 logging.getLogger（應使用 get_logger）
"""
import ast
from pathlib import Path

TARGET_FILES = [
    "web/routers/gemini.py",
    "web/app.py",
    "core/scrapers/dmm.py",
    "core/scrapers/utils.py",
    "core/scrapers/fc2.py",
    "core/scrapers/avsox.py",
    "core/scrapers/jav321.py",
    "core/scrapers/javbus.py",
    "core/scrapers/javdb.py",
    "core/scrapers/heyzo.py",
    "core/scrapers/d2pass.py",
]

def _has_logging_get_logger(path: Path) -> bool:
    """偵測檔案中是否有 logging.getLogger(...) 呼叫"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if (isinstance(func, ast.Attribute) and
                    func.attr == "getLogger" and
                    isinstance(func.value, ast.Name) and
                    func.value.id == "logging"):
                return True
    return False

def test_no_raw_logging_get_logger():
    root = Path(__file__).parent.parent.parent
    violations = []
    for rel in TARGET_FILES:
        p = root / rel
        if p.exists() and _has_logging_get_logger(p):
            violations.append(rel)
    assert violations == [], (
        f"以下檔案仍使用 logging.getLogger，請改用 get_logger：{violations}"
    )
