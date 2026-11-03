import ast
from pathlib import Path

COLLECTION_PATH = Path(__file__).resolve().parents[2] / "core" / "user_tags_write.py"


# [lint-guard: pytest-justified] Python 源碼語意（唯讀判別式必須用哪個函式判斷），
# lint 的字串比對無法排除同檔其他函式或註解誤判，需要 AST 精確鎖 apply_user_tags 函式邊界（BE-TEST-20）
class TestPostUserTagsReadonlyGuard:
    def test_post_user_tags_calls_resolve_owning_output_root(self):
        """CD-143-4: 自訂標籤寫 NFO 前必須用 config 判別唯讀來源（resolve_owning_output_root），
        不得改用 DB 的 output_dir 欄位（那是寫入後永不清除的過期標記）。"""
        assert COLLECTION_PATH.exists(), f"{COLLECTION_PATH} 不存在"
        src = COLLECTION_PATH.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(COLLECTION_PATH))

        # FunctionDef ＋ AsyncFunctionDef 一起收（既有慣例：tests/unit/test_nfo_read_boundary_guard.py
        # 的 `_find_func`）。只收前者的話，`apply_user_tags` 哪天改成 `async def` 會讓守衛
        # **假紅**——訊息還會誤導成「找不到函式定義」，逼下一個人去追一個不存在的問題。
        # 方向雖然是 fail-closed（不會假綠），但假紅一樣要付人力成本（T6 grok review P3）。
        fn = next(
            (node for node in ast.walk(tree)
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
             and node.name == "apply_user_tags"),
            None,
        )
        assert fn is not None, "未在 core/user_tags_write.py 中找到 apply_user_tags 函式定義 (fail-closed)"

        # 裸名呼叫 `resolve_owning_output_root(...)` 與屬性呼叫
        # `readonly_producer.resolve_owning_output_root(...)` 都算數——守的是「有沒有向那支
        # 單一來源提問」，不是「用哪種 import 風格寫」。只認 ast.Name 會讓後者假紅。
        calls = [
            node for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and (
                (isinstance(node.func, ast.Name) and node.func.id == "resolve_owning_output_root")
                or (isinstance(node.func, ast.Attribute) and node.func.attr == "resolve_owning_output_root")
            )
        ]
        assert calls, (
            "apply_user_tags 內未呼叫 resolve_owning_output_root()"
            "（CD-143-4：唯讀判別式必須用 config 判斷，不得改用 DB 的 output_dir 欄位）"
        )
