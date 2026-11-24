from core.gemini_client import pick_gemini_models


def model(name, key="supportedGenerationMethods", value=None):
    result = {"name": "models/" + name}
    if key is not None:
        result[key] = ["generateContent"] if value is None else value
    return result


def names(models):
    return [item["name"].removeprefix("models/") for item in models]


def test_pick_gemini_series_cap_and_order():
    lite = [f"gemini-{v}-flash-lite" for v in ("4", "3", "2", "1")]
    flash = [f"gemini-{v}-flash" for v in ("3.10", "3.9", "3.8", "2", "1")]
    gemma = [f"gemma-{v}" for v in ("5", "4", "3", "2", "1")]
    aliases = ["gemini-flash-lite-latest", "gemini-flash-latest"]
    excluded = ["gemini-99-flash-preview", "gemini-98-flash-lite-exp",
                "gemini-97-flash-image", "gemini-96-flash-tts", "gemma-95-embedding"]
    items = [model(n) for n in reversed(lite + flash + gemma + aliases + excluded + ["gemini-pro-latest"])]
    original = items[:]
    result = pick_gemini_models(items)
    assert names(result) == aliases + lite[:3] + flash[:3] + gemma
    assert items == original
    assert all(any(item is original_item for original_item in items) for item in result)


def test_pick_gemini_excludes_non_text_and_unsupported():
    items = [model("gemini-1-flash", value=["embedContent"]),
             model("gemini-2-flash", "supportedActions"),
             model("gemini-3-flash", "supported_actions"),
             model("gemini-4-flash", None),
             model("gemini-5-flash-explorer"),
             model("gemini-99-flash-exp"), model("gemini-98-flash-preview-04-17")]
    # Separate calls avoid the series cap masking a capability or token decision.
    assert names(pick_gemini_models(items[:1])) == []
    assert names(pick_gemini_models(items[1:4])) == ["gemini-4-flash", "gemini-3-flash", "gemini-2-flash"]
    assert names(pick_gemini_models(items[4:])) == ["gemini-5-flash-explorer"]
    assert names(pick_gemini_models([model("gemini-1-flash")])) == ["gemini-1-flash"]


def test_pick_gemini_collapses_numeric_suffix():
    items = [model(n) for n in ("gemini-2.5-flash-001", "gemini-2.0-flash-001", "gemini-2.5-flash")]
    assert names(pick_gemini_models(items)) == ["gemini-2.5-flash", "gemini-2.0-flash-001"]
