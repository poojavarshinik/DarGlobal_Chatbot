"""Build a searchable SQLite FTS5 database from local page JSON files."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUTS = (ROOT / "data" / "pages.json", ROOT / "data" / "pages_scraped.json")
DEFAULT_DB_PATH = ROOT / "data" / "knowledge.db"


def chunk_text(text: str, chunk_words: int = 300, overlap_words: int = 40) -> list[str]:
    """Split text into word-based chunks with a configurable overlap."""
    if chunk_words < 1 or overlap_words < 0 or overlap_words >= chunk_words:
        raise ValueError("Require chunk_words > overlap_words >= 0.")
    words = text.split()
    if not words:
        return []
    step = chunk_words - overlap_words
    return [" ".join(words[start : start + chunk_words]) for start in range(0, len(words), step)]


def _load_pages(input_paths: tuple[Path, ...]) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for path in input_paths:
        if not path.is_file():
            continue
        with path.open(encoding="utf-8") as file:
            payload = json.load(file)
        if not isinstance(payload, list):
            raise ValueError(f"{path} must contain a JSON array.")
        pages.extend(item for item in payload if isinstance(item, dict))
    return pages


def _page_chunks(page: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    text = str(page.get("text") or page.get("content") or "")
    title = str(page.get("title") or "Untitled page")
    source = str(page.get("source") or title)
    url = str(page.get("url") or "")
    return [(title, source, url, text_chunk) for text_chunk in chunk_text(text)]


def build_database(
    input_paths: tuple[Path, ...] = DEFAULT_INPUTS,
    db_path: Path = DEFAULT_DB_PATH,
) -> int:
    """Create the FTS5 table and return the number of indexed text chunks."""
    rows = [row for page in _load_pages(input_paths) for row in _page_chunks(page)]
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute("DROP TABLE IF EXISTS chunks_fts")
        connection.execute(
            """
            CREATE VIRTUAL TABLE chunks_fts USING fts5(
                title,
                source,
                url UNINDEXED,
                text,
                tokenize='unicode61'
            )
            """
        )
        connection.executemany(
            "INSERT INTO chunks_fts (title, source, url, text) VALUES (?, ?, ?, ?)",
            rows,
        )
    return len(rows)


if __name__ == "__main__":
    count = build_database()
    print(f"Indexed {count} chunks into {DEFAULT_DB_PATH}")
