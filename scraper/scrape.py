"""Polite crawler for selected public DarGlobal and Wasalt pages.

Run ``python scraper/scrape.py`` to write ``data/pages_scraped.json``.
Robots.txt is checked before each page fetch. Requests are throttled, and
redirects outside the configured host and path scope are rejected.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.robotparser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "data" / "pages_scraped.json"
USER_AGENT = "Mozilla/5.0 (compatible; AssignmentBot/1.0; educational use)"
DELAY_SECONDS = 1.5
REQUEST_TIMEOUT_SECONDS = 20

SITES: dict[str, dict[str, Any]] = {
    "DarGlobal": {
        "base": "https://darglobal.co.uk",
        "seeds": [
            "/",
            "/about",
            "/projects",
            "/investor",
            "/press",
            "/hospitality",
            "/commercial",
            "/luxury-golf-communities",
            "/tokenization",
            "/why-invest",
        ],
        "max_pages": 40,
        "allowed_paths": (
            "/",
            "/press",
            "/projects",
            "/about",
            "/investor",
            "/hospitality",
            "/commercial",
            "/luxury-golf",
            "/tokenization",
            "/why-invest",
        ),
    },
    "Wasalt": {
        "base": "https://wasalt.com",
        "seeds": ["/en/about", "/en"],
        "max_pages": 15,
        "allowed_paths": ("/en", "/en/about", "/en/corporate", "/en/s"),
    },
}

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT
_last_request_at = 0.0
_robots_cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}


def _throttled_get(url: str) -> requests.Response:
    """Make a non-redirecting request after enforcing a minimum interval."""
    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    if elapsed < DELAY_SECONDS:
        time.sleep(DELAY_SECONDS - elapsed)
    _last_request_at = time.monotonic()
    return _session.get(
        url,
        timeout=REQUEST_TIMEOUT_SECONDS,
        allow_redirects=False,
    )


def _normalize_url(url: str) -> str:
    """Remove fragments so the same page is not crawled more than once."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", parts.query, ""))


def _host_matches(url: str, base: str) -> bool:
    """Accept only HTTPS URLs on the exact configured hostname."""
    parsed = urlsplit(url)
    base_parsed = urlsplit(base)
    return (
        parsed.scheme == "https"
        and parsed.hostname is not None
        and parsed.hostname.casefold() == (base_parsed.hostname or "").casefold()
        and parsed.port in (None, 443)
    )


def _path_allowed(path: str, allowed_paths: tuple[str, ...]) -> bool:
    """Match exact paths or descendants without allowing partial-prefix matches."""
    normalized = path.rstrip("/") or "/"
    for prefix in allowed_paths:
        normalized_prefix = prefix.rstrip("/") or "/"
        if normalized == normalized_prefix:
            return True
        if normalized_prefix != "/" and normalized.startswith(normalized_prefix + "/"):
            return True
    return False


def _robots_for(base: str) -> urllib.robotparser.RobotFileParser | None:
    """Load robots rules once per host; fail closed if rules cannot be checked."""
    host = urlsplit(base).netloc.casefold()
    if host in _robots_cache:
        return _robots_cache[host]

    robots_url = urljoin(base, "/robots.txt")
    parser = urllib.robotparser.RobotFileParser()
    try:
        response = _throttled_get(robots_url)
    except requests.RequestException as exc:
        print(f"Could not check robots.txt for {base}: {exc}", file=sys.stderr)
        _robots_cache[host] = None
        return None

    if not _host_matches(response.url, base):
        print(f"robots.txt redirected outside {host}; skipping site.", file=sys.stderr)
        _robots_cache[host] = None
        return None
    if response.status_code == 404:
        parser.parse([])
    elif 200 <= response.status_code < 300:
        parser.parse(response.text.splitlines())
    else:
        print(
            f"robots.txt returned HTTP {response.status_code} for {base}; skipping site.",
            file=sys.stderr,
        )
        _robots_cache[host] = None
        return None
    _robots_cache[host] = parser
    return parser


def _clean(html: str) -> tuple[str, str, BeautifulSoup]:
    """Extract a page title and readable headings, paragraphs, and list items."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(
        ["script", "style", "noscript", "nav", "footer", "header", "svg", "form", "iframe"]
    ):
        tag.decompose()
    title = (
        BeautifulSoup(soup.title.get_text(" ", strip=True), "html.parser").get_text(" ", strip=True)
        if soup.title
        else ""
    )
    lines: list[str] = []
    for element in soup.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
        text = re.sub(r"\s+", " ", element.get_text(" ", strip=True))
        if len(text) > 2:
            lines.append(f"\n{text}" if element.name.startswith("h") else text)
    return title, "\n".join(lines), soup


def _crawl_site(name: str, config: dict[str, Any]) -> list[dict[str, str]]:
    """Crawl configured same-host URLs permitted by robots.txt and path scope."""
    base = str(config["base"])
    allowed_paths = tuple(config["allowed_paths"])
    parser = _robots_for(base)
    if parser is None:
        return []

    queue = [urljoin(base, seed) for seed in config["seeds"]]
    seen: set[str] = set()
    pages: list[dict[str, str]] = []
    while queue and len(pages) < int(config["max_pages"]):
        url = _normalize_url(queue.pop(0))
        parsed = urlsplit(url)
        if url in seen:
            continue
        seen.add(url)
        if not _host_matches(url, base) or not _path_allowed(parsed.path, allowed_paths):
            continue
        if not parser.can_fetch(USER_AGENT, url):
            print(f"robots.txt disallows {url}")
            continue

        try:
            response = _throttled_get(url)
        except requests.RequestException as exc:
            print(f"Could not fetch {url}: {exc}", file=sys.stderr)
            continue

        final_url = _normalize_url(response.url)
        final_parts = urlsplit(final_url)
        content_type = response.headers.get("content-type", "").casefold()
        if (
            response.status_code != 200
            or "text/html" not in content_type
            or not _host_matches(final_url, base)
            or not _path_allowed(final_parts.path, allowed_paths)
            or not parser.can_fetch(USER_AGENT, final_url)
        ):
            if response.status_code != 200:
                print(f"Skipping {url}: HTTP {response.status_code}", file=sys.stderr)
            if response.status_code == 200 and not _host_matches(final_url, base):
                print(f"Redirect left the configured host; skipped {url}", file=sys.stderr)
            elif 300 <= response.status_code < 400:
                print(f"Skipping redirect from {url}; crawl its destination directly if in scope.")
            continue

        title, text, soup = _clean(response.text)
        if len(text) > 200:
            pages.append(
                {"source": name, "url": final_url, "title": title, "text": text}
            )
            print(f"[{name}] {final_url} ({len(text)} chars)")

        for anchor in soup.find_all("a", href=True):
            link = _normalize_url(urljoin(final_url, anchor["href"]))
            link_parts = urlsplit(link)
            if (
                _host_matches(link, base)
                and _path_allowed(link_parts.path, allowed_paths)
                and link not in seen
            ):
                queue.append(link)
    return pages


def scrape_pages() -> list[dict[str, str]]:
    """Crawl the configured sites and write extracted text to the data directory."""
    _robots_cache.clear()
    pages: list[dict[str, str]] = []
    for name, config in SITES.items():
        pages.extend(_crawl_site(name, config))
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(pages, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return pages


if __name__ == "__main__":
    result = scrape_pages()
    print(f"Saved {len(result)} pages to {OUTPUT_PATH}")
