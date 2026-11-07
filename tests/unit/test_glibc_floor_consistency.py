import ast
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


# [lint-guard: pytest-justified] 三個檔案之間的契約（Python 常數／bash 賦值／中文句），lint 字串指紋表達不了「三處取值相等」
def _audit_floor(root):
    tree = ast.parse((root / "scripts/audit_build_artifact.py").read_text(encoding="utf-8"))
    hits = [n.value for n in tree.body if isinstance(n, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id == "GLIBC_FLOOR" for t in n.targets)]
    assert len(hits) == 1, "audit_build_artifact.py: 模組層 GLIBC_FLOOR 賦值不是恰好一處"
    tup = hits[0]
    assert isinstance(tup, ast.Tuple) and len(tup.elts) == 2 and all(
        isinstance(e, ast.Constant) and isinstance(e.value, int) for e in tup.elts
    ), "audit_build_artifact.py: GLIBC_FLOOR 不是 (int, int)"
    return tuple(e.value for e in tup.elts)


def _installer_floor(root):
    hits = re.findall(r"^GLIBC_FLOOR=(\d+)\.(\d+)$", (root / "install.sh").read_text(encoding="utf-8"), re.MULTILINE)
    assert len(hits) == 1, "install.sh: 抽不出恰好一行 GLIBC_FLOOR=<主>.<次>"
    return tuple(int(x) for x in hits[0])


def _doc_floor(root):
    text = (root / "docs/linux-server.md").read_text(encoding="utf-8")
    hits = re.findall(r"glibc\s*(\d+)\.(\d+)(\s*以上)?", text)
    assert hits, "docs/linux-server.md: 抽不出任何 glibc <主>.<次>"
    assert any(h[2] for h in hits), "docs/linux-server.md: 沒有「glibc X.Y 以上」這種下限句"
    assert len({h[:2] for h in hits}) == 1, "docs/linux-server.md: 出現多個不同的 glibc 版本號"
    return tuple(int(x) for x in hits[0][:2])


def test_glibc_floor_same_in_audit_installer_and_doc():
    audit, installer, doc = _audit_floor(_REPO_ROOT), _installer_floor(_REPO_ROOT), _doc_floor(_REPO_ROOT)
    assert audit == installer == doc, f"glibc 下限不一致：審核器={audit} 安裝器={installer} 文件={doc}"
