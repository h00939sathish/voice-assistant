"""
Researcher — Lightweight web search and page fetching using stdlib only.
No API keys, no Playwright. Uses DuckDuckGo HTML search + urllib.
"""

import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

# ── HTML Stripping ─────────────────────────────────────────────────────


class _TextExtractor(HTMLParser):
    """Strip HTML tags and extract readable text, skipping script/style/nav blocks."""

    SKIP_TAGS = {
        "script",
        "style",
        "head",
        "nav",
        "footer",
        "header",
        "aside",
        "noscript",
        "form",
        "button",
        "svg",
        "meta",
        "link",
    }
    BLOCK_TAGS = {
        "p",
        "div",
        "article",
        "section",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "tr",
        "td",
        "br",
        "blockquote",
    }

    def __init__(self):
        super().__init__()
        self.text_parts: list[str] = []
        self._skip_depth = 0
        self._skip_tag: str | None = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
            self._skip_tag = tag
        elif tag in self.BLOCK_TAGS and self.text_parts and self.text_parts[-1] != "\n":
            self.text_parts.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            text = data.strip()
            if text:
                self.text_parts.append(text + " ")

    def get_text(self) -> str:
        raw = "".join(self.text_parts)
        # Collapse multiple blank lines
        return re.sub(r"\n{3,}", "\n\n", raw).strip()


class _LinkExtractor(HTMLParser):
    """Extract all <a href> links from HTML."""

    def __init__(self, base_url: str = ""):
        super().__init__()
        self.links: list[dict[str, str]] = []
        self.base_url = base_url

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            attrs_dict = dict(attrs)
            href = attrs_dict.get("href", "")
            text = attrs_dict.get("title", "")
            if href and href.startswith("http"):
                self.links.append({"url": href, "text": text})


def strip_html(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass
    return parser.get_text()


def extract_links_from_html(html: str, base_url: str = "") -> list[dict[str, str]]:
    parser = _LinkExtractor(base_url)
    try:
        parser.feed(html)
    except Exception:
        pass
    return parser.links


# ── HTTP Client ────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def _http_get(url: str, timeout: int = 10) -> tuple[str | None, str | None]:
    """Fetch URL, return (html_content, error_message)."""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            charset = "utf-8"
            content_type = resp.headers.get("Content-Type", "")
            m = re.search(r"charset=([^\s;]+)", content_type)
            if m:
                charset = m.group(1).strip()
            return resp.read().decode(charset, errors="replace"), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return None, f"URL error: {e.reason}"
    except Exception as e:
        return None, f"Error: {e}"


# ── Search ─────────────────────────────────────────────────────────────


def search_web(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Search DuckDuckGo and return structured results (no API key needed)."""
    encoded = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded}"

    html, err = _http_get(url)
    if err or not html:
        return [{"error": err or "No response"}]

    # Parse DuckDuckGo HTML results
    results = []
    # Match result blocks: title + URL + snippet
    title_pattern = re.compile(r'class="result__a"[^>]*>([^<]+)</a>', re.DOTALL)
    url_pattern = re.compile(r'class="result__url"[^>]*>([^<]+)<', re.DOTALL)
    snippet_pattern = re.compile(r'class="result__snippet"[^>]*>(.*?)</a>', re.DOTALL)

    titles = title_pattern.findall(html)
    urls_raw = url_pattern.findall(html)
    snippets = snippet_pattern.findall(html)

    for i in range(min(len(titles), len(urls_raw), max_results)):
        raw_url = urls_raw[i].strip()
        if not raw_url.startswith("http"):
            raw_url = "https://" + raw_url

        snippet = (
            re.sub(r"<[^>]+>", "", snippets[i]).strip() if i < len(snippets) else ""
        )
        results.append(
            {
                "title": titles[i].strip(),
                "url": raw_url,
                "snippet": snippet,
            }
        )

    return results if results else [{"message": "No results found"}]


# ── Page Fetch ─────────────────────────────────────────────────────────


def fetch_page(url: str, max_chars: int = 6000) -> dict[str, str]:
    """Fetch a URL and return clean extracted text."""
    if not url.startswith("http"):
        url = "https://" + url

    html, err = _http_get(url)
    if err:
        return {"url": url, "error": err, "text": ""}

    text = strip_html(html)
    links = extract_links_from_html(html, url)

    # Trim to max_chars
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n[... content truncated at {max_chars} chars]"

    return {
        "url": url,
        "char_count": len(text),
        "text": text,
        "link_count": len(links),
    }


def extract_links(url: str, max_links: int = 20) -> dict:
    """Fetch a URL and return all hyperlinks found on the page."""
    if not url.startswith("http"):
        url = "https://" + url

    html, err = _http_get(url)
    if err:
        return {"url": url, "error": err, "links": []}

    links = extract_links_from_html(html, url)
    return {
        "url": url,
        "total_links": len(links),
        "links": links[:max_links],
    }
