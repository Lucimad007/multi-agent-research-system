from langchain_core.tools import tool

_BACKENDS = ("auto", "wikipedia")


def _queries(query: str) -> list[str]:
    words = query.split()
    variants = [query]
    for size in (6, 4):
        if len(words) > size:
            variants.append(" ".join(words[:size]))
    return variants


def _hits(query: str) -> list[dict]:
    from ddgs import DDGS

    last_error = "No results found."
    for text in _queries(query):
        for backend in _BACKENDS:
            try:
                hits = list(DDGS(timeout=20).text(text, max_results=8, backend=backend))
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
