from langchain_core.tools import tool


@tool
def web_search(query: str) -> str:
    """Search the public web and return titles, URLs, and snippets."""
    from ddgs import DDGS

    hits = list(DDGS().text(query, max_results=8))
    if not hits:
        return "No results."

    lines: list[str] = []
    for hit in hits:
        title = hit.get("title") or "Untitled"
        url = hit.get("href") or ""
        snippet = hit.get("body") or ""
        lines.append(f"{title}\n{url}\n{snippet}")
    return "\n\n".join(lines)
