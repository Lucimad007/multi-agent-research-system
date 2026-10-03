import re
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from urllib.request import Request, urlopen

from langchain_core.tools import tool

_BACKENDS = ("auto", "wikipedia")


def _hits(query: str) -> list[dict]:
    from ddgs import DDGS

    text = " ".join(query.split())[:120]
    last_error = "No results found."
    for backend in _BACKENDS:
        try:
            hits = list(DDGS(timeout=8).text(text, max_results=5, backend=backend))
        except Exception as exc:
            last_error = str(exc)
            continue
        if hits:
            return hits
    raise RuntimeError(last_error)


@tool
def web_search(query: str) -> str:
    """Search the public web and return titles, URLs, and snippets."""
    compact = " ".join(query.split())[:180]
    try:
        hits = _hits(compact)
    except Exception as exc:
        return f"No results for this query. Try a shorter query. Cause: {exc}"

    lines: list[str] = []
    for hit in hits:
        title = hit.get("title") or "Untitled"
        url = hit.get("href") or ""
        snippet = hit.get("body") or ""
        lines.append(f"{title}\n{url}\n{snippet}")
    return "\n\n".join(lines)


class _VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self.parts.append(data)


def excerpt_from_html(raw: str, limit: int = 320) -> str:
    """Keep a short slice of visible page text, preferring a passage that states a number."""
    parser = _VisibleText()
    try:
        parser.feed(raw)
    except Exception:
        return ""
    text = re.sub(r"\s+", " ", " ".join(parser.parts)).strip()
    if not text:
        return ""
    window = re.search(r".{0,60}\d[\d,.]{1,}.{0,180}", text)
    chosen = window.group(0) if window else text
    return chosen[:limit].strip()


def page_excerpt(url: str) -> str:
    if not url.startswith("http"):
        return ""
    request = Request(url, headers={"User-Agent": "research-desk/1.0"})
    try:
        with urlopen(request, timeout=6) as response:
            raw = response.read(60_000).decode("utf-8", "ignore")
    except Exception:
        return ""
    return excerpt_from_html(raw)


def collect_sources(query: str) -> list[dict]:
    """Turn a web search into source records. Returns an empty list instead of raising."""
    text = str(web_search.invoke(query))
    sources: list[dict] = []
    seen: set[str] = set()
    for block in text.split("\n\n"):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2 or not lines[1].startswith("http") or lines[1] in seen:
            continue
        seen.add(lines[1])
        summary = lines[2] if len(lines) > 2 else "The search result did not include a snippet."
        sources.append({"title": lines[0], "url": lines[1], "summary": summary})
    if not sources:
        return []

    def enrich(source: dict) -> dict:
        excerpt = page_excerpt(source["url"])
        summary = source["summary"]
        if excerpt:
            summary = f"{excerpt} {summary}"
        source["summary"] = summary[:480]
        return source

    with ThreadPoolExecutor(max_workers=3) as pool:
        enriched = list(pool.map(enrich, sources[:3]))
    tail = sources[3:5]
    for source in tail:
        source["summary"] = source["summary"][:240]
    return enriched + tail
