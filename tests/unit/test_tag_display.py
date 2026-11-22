import pytest

from core.tag_display import build_context, display_tags


@pytest.mark.parametrize(
    ("blacklist", "alias_groups", "must_hidden", "must_visible"),
    [
        pytest.param(
            ["中文字幕"], [], [], ["中文字幕", "中字"], id="badge-direct-no-group"
        ),
        pytest.param(
            ["ハイビジョン"],
            [["中文字幕", "ハイビジョン"]],
            [],
            ["中文字幕", "ハイビジョン", "中字"],
            id="badge-primary-same-group",
        ),
        pytest.param(
            ["ハイビジョン"],
            [["ハイビジョン", "中文字幕"]],
            [],
            ["ハイビジョン", "中文字幕"],
            id="badge-alias-same-group",
        ),
        pytest.param(
            ["フェラ"], [["口交", "フェラ"]], ["フェラ", "口交"], [], id="plain-group-expands"
        ),
        pytest.param(
            ["ハイビジョン"], [], ["ハイビジョン"], ["口交"], id="no-group-only-itself"
        ),
    ],
)
def test_protected_words_never_hidden(
    blacklist, alias_groups, must_hidden, must_visible
):
    ctx = build_context(blacklist, alias_groups)
    for word in must_hidden:
        assert word.strip().lower() in ctx.hidden
    for word in must_visible:
        assert word.strip().lower() not in ctx.hidden


@pytest.mark.parametrize(
    ("tags", "blacklist", "alias_groups", "expected"),
    [
        pytest.param(
            ["フェラ", "口交"], [], [["口交", "フェラ"]], ["口交"], id="alias-to-primary"
        ),
        pytest.param(
            ["中出し", "内射"],
            [],
            [["中出", "中出し", "内射"]],
            ["中出"],
            id="merge-dedup",
        ),
        pytest.param(
            ["ハイビジョン", "口交"],
            ["ハイビジョン"],
            [],
            ["口交"],
            id="blacklist-masked",
        ),
        pytest.param(
            ["原創", "口交"],
            [],
            [["口交", "フェラ"]],
            ["原創", "口交"],
            id="ungrouped-kept",
        ),
        pytest.param(
            ["口交", "フェラ", "原創"],
            [],
            [["口交", "フェラ"]],
            ["口交", "原創"],
            id="order-kept",
        ),
        pytest.param(["AA", "BB"], [], [], ["AA", "BB"], id="both-empty-identity"),
        pytest.param(["   ", "口交"], [], [], ["口交"], id="blank-dropped"),
        pytest.param(["高畫質", "中出"], [], [["4K", "高畫質"]], ["中出"], id="4K-primary-dropped"),
    ],
)
def test_display_tags_table(tags, blacklist, alias_groups, expected):
    ctx = build_context(blacklist, alias_groups)
    assert display_tags(tags, ctx) == expected


def test_suggestions_not_protected():
    from core.cover_attributes import protected_tag_words
    from core.tag_display import COMMON_BLACKLIST_SUGGESTIONS

    assert len(COMMON_BLACKLIST_SUGGESTIONS) == 8
    keys = [s.strip().lower() for s in COMMON_BLACKLIST_SUGGESTIONS]
    assert len(set(keys)) == len(keys)
    protected = protected_tag_words()
    assert set(keys).isdisjoint(protected)
    ctx = build_context(list(COMMON_BLACKLIST_SUGGESTIONS), [], protected=protected)
    assert set(keys) <= set(ctx.hidden)
