"""
MARS Tool — Web Search via DuckDuckGo (no API key required).

Returns top results as a formatted string for LLM consumption.
Fallback: returns an error string (never raises) so the ReAct loop can continue.
"""
import logging

logger = logging.getLogger(__name__)


def web_search(query: str, max_results: int = 5) -> str:
    """
    Search the web using DuckDuckGo.

    Args:
        query: Natural-language search query.
        max_results: Number of results to return (default: 5).

    Returns:
        Formatted string of results or an error message.
    """
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))

        if not results:
            return f"No web results found for: {query}"

        lines = [f"Web search results for: '{query}'\n"]
        for i, r in enumerate(results, 1):
            title = r.get("title", "No title")
            body = r.get("body", "No snippet")
            href = r.get("href", "")
            lines.append(f"{i}. **{title}**\n   {body}\n   Source: {href}\n")

        return "\n".join(lines)

    except Exception as exc:
        logger.warning("web_search failed: %s", exc)
        return f"Web search failed: {exc}"
