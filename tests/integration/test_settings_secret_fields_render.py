"""[lint-guard: pytest-justified] 巨集展開結果無法由模板靜態掃描驗證。"""
import re
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
    assert "api-key-alert" not in html
    assert "API Key 將以明文存儲" not in html
    parser = SecretFieldsParser()
    parser.feed(html)
    assert sorted(field[0] for field in parser.fields) == sorted(
        ["gemini", "claude", "openaiOfficial", "openai", "aiSimilar", "aiFaces", "metatube"]
    )
    assert len(re.findall(r'(?<![\w:-])type="password"', html)) == 7
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
    assert html.count("aistudio.google.com/apikey") == 1
