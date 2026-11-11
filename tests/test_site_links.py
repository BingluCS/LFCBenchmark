"""Check that the published page's local navigation and download targets exist."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

SITE = Path(__file__).resolve().parents[1] / "docs"


class PageLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.urls = set(), []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            assert attrs["id"] not in self.ids, f"duplicate id: {attrs['id']}"
            self.ids.add(attrs["id"])
        for name in ("href", "src"):
            if attrs.get(name):
                self.urls.append(attrs[name])


def test_static_site_links_resolve():
    page = PageLinks()
    page.feed((SITE / "index.html").read_text(encoding="utf-8"))
    for url in page.urls:
        parsed = urlsplit(url)
        if parsed.scheme or parsed.netloc:
            continue
        if parsed.path:
            assert (SITE / unquote(parsed.path)).exists(), url
        elif parsed.fragment:
            assert unquote(parsed.fragment) in page.ids, url
