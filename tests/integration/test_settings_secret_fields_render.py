"""[lint-guard: pytest-justified] 巨集展開結果無法由模板靜態掃描驗證。"""
import re
from collections import Counter
from html.parser import HTMLParser


class SecretFieldsParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.current = None
        self.fields = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "div":
            if self.current is not None:
                self.depth += 1
            elif "data-secret-field" in attrs:
                self.current = [attrs["data-secret-field"], 0, False, []]
                self.depth = 1
                self.fields.append(self.current)
        if self.current is not None:
            if "x-text" in attrs:
                self.current[3].append(attrs["x-text"])
            if tag == "input" and re.search(r'(?<![\w:-])type="password"', self.get_starttag_text()):
                self.current[1] += 1
            if "bi-eye" in (attrs.get("class") or ""):
                self.current[2] = True

    def handle_endtag(self, tag):
        if tag == "div" and self.current is not None:
            self.depth -= 1
            if self.depth == 0:
                self.current = None


def test_settings_renders_seven_secret_fields_without_warning(client):
    response = client.get("/settings")
    assert response.status_code == 200
    html = response.text
    parser = SecretFieldsParser()
    parser.feed(html)
    assert sorted(field[0] for field in parser.fields) == sorted(
        ["gemini", "claude", "openaiOfficial", "openai"] * 2
        + ["aiSimilar", "aiFaces", "metatube"]
    )
    assert len(re.findall(r'(?<![\w:-])type="password"', html)) == 11
    assert all(count == 1 and not eye for _, count, eye, _ in parser.fields)
    for field, _, _, texts in parser.fields:
        text = " ".join(texts)
        for action in ("will_clear", "will_save"):
            base = f"settings.secret.{action}'"
            connect = f"settings.secret.{action}_connect'"
            if field == "metatube":
                assert connect in text
                assert base not in text
            else:
                assert base in text
                assert connect not in text
    assert html.count("aistudio.google.com/apikey") == 2


class ConnectionIdsParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.gemini_count = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if attrs.get("data-ai-conn") == "gemini":
            self.gemini_count += 1

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)


def test_settings_ai_connections_have_unique_ids(client):
    response = client.get("/settings")
    assert response.status_code == 200
    html = response.text
    parser = ConnectionIdsParser()
    parser.feed(html)
    ids = Counter(parser.ids)
    assert all(count == 1 for count in ids.values())
    for base in (
        "aiConnections", "geminiApiKey", "claudeApiKey", "openaiOfficialApiKey",
        "openaiApiKey", "ollamaUrl", "testOllamaBtn", "testGeminiBtn", "testClaudeBtn",
        "testOpenaiOfficialBtn", "openaiOfficialStatus",
    ):
        assert ids[base] == 1
        assert ids[f"tags-{base}"] == 1
    assert parser.gemini_count == 2
    assert html.count("settings.ai.connections_title") == 2
    assert html.count("settings.translate.gemini_free_hint") == 2
