---
title: DarGlobal and Wasalt Assistant
emoji: 🏢
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 8501
pinned: false
---

# DarGlobal & Wasalt Assistant

A Streamlit chatbot that answers questions about **DarGlobal** (luxury real estate developer) and **Wasalt** (Saudi real estate portal). It has two modes: a local **Knowledge Base** built from public pages, and a web-backed **Live Search**.


## Architecture

`scrape -> chunk -> SQLite FTS5 -> retrieve -> OpenRouter`

- `scraper/scrape.py` fetches a bounded set of public pages. It checks each site's `robots.txt`, throttles requests, limits crawling to explicit path prefixes, and skips any page that blocks automated access.
- `scraper/build_db.py` reads `data/pages.json` (and `data/pages_scraped.json` when present) and builds overlapping ~300-word chunks in `data/knowledge.db`.
- `core/retriever.py` searches the chunks with SQLite FTS5 and BM25, preferring the company named in the question.
- `core/live_search.py` queries Serper.dev, includes the organic results, and optionally fetches the top two public pages.
- `core/llm.py` sends the supplied context and recent chat history to OpenRouter, with fallback across several free models.

## Modes

- **Knowledge Base:** retrieves up to five relevant chunks from the locally stored pages and answers only from them, with source links.
- **Live Search:** searches the web at question time through Serper.dev and answers from the results. It is limited to 10 searches per session per 10 minutes. If the Serper key is missing or a search fails, the chat says so and suggests switching to Knowledge Base.

In both modes the app does the retrieval or search itself and passes the results to the model as context. It does not rely on model tool-calling, which is inconsistent on free models. If the context does not contain the answer, the bot says so instead of guessing.

## Data sources and limitations

- **Scope:** only publicly accessible pages from DarGlobal (darglobal.co.uk) and Wasalt (wasalt.sa / wasalt.com): company overview, projects, press releases, services and auction terms. No logins and no private or personal data.
- **Snapshot:** the data was collected in November 2026 and will go out of date. Some figures differ between sources (for example DarGlobal's city and country counts), and the bot is instructed to point out such differences.
- **Wasalt:** Wasalt's website returns a Cloudflare challenge (HTTP 403) to automated requests. I did not try to bypass it. Wasalt content in the knowledge base was curated from its publicly accessible official pages and public press releases, and Live Search covers anything missing.
- **Search quality:** FTS5 is keyword-based and can miss semantic matches. Live Search page extraction is best-effort and capped at 3,000 characters per page.
- **Models:** free OpenRouter models can be rate-limited or change over time, so the app tries the configured fallback models in order.

## Add or update data

Put a JSON array of page records in `data/pages.json`. Each record uses `source`, `title`, `url` and `text` (or `content`):

```json
[
  {
    "source": "DarGlobal",
    "title": "Example page title",
    "url": "https://www.example.com/public-page",
    "text": "Text collected from the public page."
  }
]
```

Then rebuild the database:

```powershell
python scraper/scrape.py      # optional: fetch public pages
python scraper/build_db.py    # build data/knowledge.db
```

### Scraping scope and ethics

Only collect publicly accessible pages. Respect `robots.txt`, site terms and reasonable request rates. Do not log in, bypass access controls, or collect private information.

## Local run

Use Python 3.11:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `OPENROUTER_API_KEY`, `SERPER_API_KEY`, and optionally `OPENROUTER_MODEL` and `OPENROUTER_FALLBACK_MODELS` in `.env`, then:

```powershell
python scraper/build_db.py
streamlit run app.py
pytest -q
```

The app also reads the same names from Streamlit secrets. Never commit `.env` or any key.

## Docker

The image includes `data/pages.json` and builds `data/knowledge.db` during the build.

```powershell
docker build -t darglobal-wasalt-assistant .
docker run --rm -p 8501:8501 --env-file .env darglobal-wasalt-assistant
```

Open http://localhost:8501.

## Deployment (Hugging Face Spaces)

1. Create a new Space, choose **Docker** as the SDK and **Public** visibility. The settings block at the top of this README sets `sdk: docker` and `app_port: 8501`.
2. In **Settings > Variables and secrets**, add `OPENROUTER_API_KEY` and `SERPER_API_KEY` as **secrets**, and `OPENROUTER_MODEL` and `OPENROUTER_FALLBACK_MODELS` as **variables**.
3. Push this repository to the Space (`git push space main`). The Space builds the Dockerfile and starts the app automatically.

## Future improvements

Embedding-based or hybrid retrieval, scheduled re-scraping, source freshness metadata, caching for repeated questions, and more integration tests.