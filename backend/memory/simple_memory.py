"""
MARS-Lite — Simple JSON File Memory.

Stores the most recent query context for visualization purposes only.
No embeddings. No vector search. No external services.

Schema:
  {
    "last_query":    str,
    "last_category": str,   # inferred from query keywords
    "last_budget":   str | null,
    "timestamp":     ISO-8601 str,
    "history":       [ { same fields } ]  — last 10 entries
  }
"""
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DATA_DIR  = Path(__file__).resolve().parent.parent.parent / "data"
MEMORY_FILE = DATA_DIR / "memory.json"

_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "AI/ML":      ["ai", "llm", "machine learning", "neural", "gpt", "rag", "agent", "model", "transformer"],
    "Finance":    ["budget", "cost", "price", "market", "stock", "crypto", "invest", "revenue", "profit"],
    "Science":    ["physics", "chemistry", "biology", "quantum", "space", "climate", "research"],
    "Technology": ["software", "hardware", "cloud", "database", "api", "framework", "python", "javascript"],
    "Health":     ["medicine", "health", "treatment", "disease", "drug", "hospital", "symptom"],
}


def _infer_category(query: str) -> str:
    q = query.lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in q for kw in keywords):
            return category
    return "General"


def _extract_budget(query: str) -> Optional[str]:
    """Try to extract a dollar/budget value from the query."""
    match = re.search(r"\$[\d,]+(?:\.\d+)?(?:k|m|b)?|\b\d+(?:,\d+)*(?:\.\d+)?\s*(?:dollars?|usd|million|billion)\b", query, re.IGNORECASE)
    return match.group() if match else None


import threading

_memory_lock = threading.RLock()


def _load() -> dict:
    """Read memory from disk, returning empty structure on failure."""
    with _memory_lock:
        try:
            if MEMORY_FILE.exists():
                return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not read memory file: %s", exc)
        return {"last_query": None, "last_category": None, "last_budget": None, "timestamp": None, "history": []}


def _save(data: dict) -> None:
    """Persist memory to disk."""
    with _memory_lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            MEMORY_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("Could not save memory: %s", exc)


def store(query: str) -> dict:
    """
    Store query context after a successful run.
    Returns the updated memory snapshot.
    """
    with _memory_lock:
        current = _load()
        entry = {
            "last_query":    query,
            "last_category": _infer_category(query),
            "last_budget":   _extract_budget(query),
            "timestamp":     datetime.now(timezone.utc).isoformat(),
        }

        # Prepend to history (keep last 10)
        history = current.get("history", [])
        history.insert(0, entry)
        history = history[:10]

        data = {**entry, "history": history}
        _save(data)
        logger.info("Memory stored: category=%s query=%s", entry["last_category"], query[:60])
        return data


def retrieve() -> dict:
    """Return current memory contents."""
    with _memory_lock:
        return _load()


def clear() -> None:
    """Reset memory to empty."""
    with _memory_lock:
        _save({"last_query": None, "last_category": None, "last_budget": None, "timestamp": None, "history": []})
        logger.info("Memory cleared")
