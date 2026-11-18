"""SQLite FTS5 retrieval for the local company knowledge base."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "knowledge.db"
_WORD_PATTERN = re.compile(r"[^\W_]+", flags=re.UNICODE)


@dataclass(frozen=True)
class Chunk:
    """A retrieved, attributable passage from a source page."""

    title: str
    source: str
    url: str
    text: str


def build_fts_query(question: str) -> str:
    """Convert natural-language text into a safe OR query for SQLite FTS5."""
    terms = _WORD_PATTERN.findall(question)
    return " OR ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms)


def search_chunks(
    question: str,
    db_path: str | Path = DEFAULT_DB_PATH,
    limit: int = 5,
) -> list[Chunk]:
    """Return matching chunks ranked by FTS5 BM25, preferring named companies."""
    query = build_fts_query(question)
    if not query or limit < 1:
        return []

    normalized_question = question.casefold()
    preferred_source = None
    if "wasalt" in normalized_question:
        preferred_source = "wasalt"
    elif "darglobal" in normalized_question or "dar global" in normalized_question:
        preferred_source = "darglobal"

    path = Path(db_path)
    if not path.is_file():
        return []
    with sqlite3.connect(path) as connection:
        try:
            rows = connection.execute(
                """
                SELECT title, source, url, text
                FROM chunks_fts
                WHERE chunks_fts MATCH ?
                ORDER BY
                    CASE
                        WHEN ? = 'wasalt' AND lower(source) LIKE '%wasalt%' THEN 0
                        WHEN ? = 'darglobal' AND lower(source) LIKE '%darglobal%' THEN 0
                        ELSE 1
                    END,
                    bm25(chunks_fts, 2.0, 1.0, 0.0, 1.0)
                LIMIT ?
                """,
                (query, preferred_source, preferred_source, limit),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                return []
            raise
    return [Chunk(title=row[0], source=row[1], url=row[2], text=row[3]) for row in rows]
