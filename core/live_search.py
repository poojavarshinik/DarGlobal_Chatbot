"""Serper.dev search and optional extraction of public result pages."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import MutableSequence
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

SERPER_URL = "https://google.serper.dev/search"
SEARCH_WINDOW_SECONDS = 10 * 60
MAX_SEARCHES_PER_WINDOW = 10
_USER_AGENT = "DarGlobalWasaltAssistant/1.0 (public-page research)"


@dataclass(frozen=True)
class SearchSource:
    """A web search result with optional extracted page text."""

    title: str
    snippet: str
    url: str
    page_text: str = ""


@dataclass(frozen=True)
class LiveSearchResult:
    """Search context and user-facing status from a live search attempt."""

    sources: list[SearchSource]
    context: str
    message: str = ""


def build_search_query(question: str) -> str:
    """Add company-specific site filters when the question names a company."""
    lowered = question.casefold()
    domains: list[str] = []
    if "darglobal" in lowered or "dar global" in lowered:
        domains.append("site:darglobal.co.uk")
    if "wasalt" in lowered:
        domains.append("site:wasalt.com OR site:wasalt.sa")
    if not domains:
        domains = ["(site:darglobal.co.uk OR site:wasalt.com OR site:wasalt.sa)"]
    return f"{question} {' '.join(domains)}"


def _extract_page_text(url: str) -> str:
    """Fetch a public result page and return a bounded amount of readable text."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    response = requests.get(
        url,
        headers={"User-Agent": _USER_AGENT},
        timeout=8,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for element in soup(["script", "style", "noscript", "svg", "header", "footer", "nav"]):
        element.decompose()
    return " ".join(soup.stripped_strings)[:3000]


def search_live(
    question: str,
    api_key: str,
    recent_searches: MutableSequence[float],
) -> LiveSearchResult:
    """Search Serper, fetch up to two result pages, and enforce a session rate limit."""
    if not api_key:
        return LiveSearchResult(
            [],
            "",
            "Live Search needs a SERPER_API_KEY. Add it to your environment or Streamlit secrets, "
            "or switch to Knowledge Base mode.",
        )

    now = time.time()
    recent_searches[:] = [
        timestamp for timestamp in recent_searches if now - timestamp < SEARCH_WINDOW_SECONDS
    ]
    if len(recent_searches) >= MAX_SEARCHES_PER_WINDOW:
        return LiveSearchResult(
            [],
            "",
            "Live Search is limited to 10 searches per 10 minutes per session. "
            "Please wait or use Knowledge Base mode.",
        )
    recent_searches.append(now)

    try:
        response = requests.post(
            SERPER_URL,
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": build_search_query(question), "num": 6},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        return LiveSearchResult(
            [],
            "",
            f"Serper.dev search failed ({exc}). Check the API key or switch to Knowledge Base mode.",
        )

    if not isinstance(payload, dict):
        return LiveSearchResult([], "", "Serper.dev returned an invalid response. Try Knowledge Base mode.")

    organic = payload.get("organic", [])
    if not isinstance(organic, list):
        organic = []
    sources: list[SearchSource] = []
    for item in organic[:6]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "Untitled result")
        snippet = str(item.get("snippet") or "")
        url = str(item.get("link") or "")
        page_text = ""
        if len(sources) < 2 and url:
            try:
                page_text = _extract_page_text(url)
            except requests.RequestException:
                page_text = ""
        sources.append(SearchSource(title=title, snippet=snippet, url=url, page_text=page_text))

    context = "\n\n".join(
        f"Source: {source.title}\nURL: {source.url}\n"
        f"Search snippet: {source.snippet}\nFetched page text: {source.page_text or '[not available]'}"
        for source in sources
    )
    return LiveSearchResult(sources, context)
