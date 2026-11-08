"""T1: d2pass number gate — 真值表＋派發計數."""

from core.scrapers.d2pass import D2PassScraper


def _patched_counts(monkeypatch, scraper):
    counts = {"fetch": 0, "html": 0}

    def fake_fetch(site, movie_id):
        counts["fetch"] += 1
        return None

    def fake_html(movie_id):
        counts["html"] += 1
        return None

    monkeypatch.setattr(scraper, "_fetch_json", fake_fetch)
    monkeypatch.setattr(scraper, "_parse_caribbeancom_html", fake_html)
    return counts


def test_is_d2pass_number_truth_table():
    from core.scrapers.d2pass import is_d2pass_number

    accepts = ["011225_01", "070116-197", "120415_201", "082912_01", "122211_01", "051515-877"]
    rejects = ["IPZZ-943", "SSIS-001", "300MIUM-123", "FC2-123456", "HEYZO-1234", "N0762"]
    for n in accepts:
        assert is_d2pass_number(n), n
    for n in rejects:
        assert not is_d2pass_number(n), n


def test_search_dispatch_requests(monkeypatch):
    scraper1 = D2PassScraper()
    counts1 = _patched_counts(monkeypatch, scraper1)
    assert scraper1.search("IPZZ-943") is None
    assert counts1["fetch"] == 0, counts1
    assert counts1["html"] == 0, counts1

    scraper2 = D2PassScraper()
    counts2 = _patched_counts(monkeypatch, scraper2)
    scraper2.search("011225_01")
    assert counts2["fetch"] >= 1, counts2
