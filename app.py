"""Streamlit chatbot for DarGlobal and Wasalt company information."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import streamlit as st
from dotenv import load_dotenv

from core.llm import answer_question
from core.live_search import search_live
from core.retriever import Chunk, search_chunks

load_dotenv()

ROOT = Path(__file__).resolve().parent
MODES = ("Knowledge Base", "Live Search")
EXAMPLE_QUESTIONS = (
    "What projects does DarGlobal have in Oman?",
)


def get_setting(name: str, default: str = "") -> str:
    """Read configuration from the environment, falling back to Streamlit secrets."""
    value = os.getenv(name)
    if value:
        return value
    try:
        secret = st.secrets.get(name, default)
    except (AttributeError, FileNotFoundError):
        return default
    return str(secret) if secret else default


def format_chunks(chunks: list[Chunk]) -> str:
    """Format retrieved chunks as attributable context for the LLM."""
    return "\n\n".join(
        f"Source: {chunk.source}\nTitle: {chunk.title}\nURL: {chunk.url}\n"
        f"Content: {chunk.text}"
        for chunk in chunks
    )


def render_message(message: dict[str, Any]) -> None:
    """Render one stored chat message and its source list."""
    with st.chat_message(message["role"]):
        if message["role"] == "assistant" and message.get("mode"):
            if message["mode"] == "Greeting":
                st.caption("General greeting")
            else:
                st.caption(f"Answered using {message['mode']}")
        st.markdown(message["content"])
        if message.get("notice"):
            st.info(message["notice"])
        if message.get("sources"):
            with st.expander("Sources"):
                for source in message["sources"]:
                    title = source.get("title") or source.get("source") or "Source"
                    url = source.get("url", "")
                    st.markdown(f"- [{title}]({url})" if url else f"- {title}")


def main() -> None:
    """Run the Streamlit chat interface."""
    st.set_page_config(page_title="DarGlobal & Wasalt Assistant", page_icon="🏙️")
    st.title("DarGlobal & Wasalt Assistant")
    st.caption("Ask questions about DarGlobal and the Wasalt.")

    with st.sidebar:
        st.header("Chat settings")
        mode = st.radio("Mode", MODES, index=0)
        if mode == "Knowledge Base":
            st.caption("Answers generated using pre-scraped and indexed web data.")
        else:
            st.caption("Searches the web in real time to retrieve relevant information and answer your questions.")
        if st.button("Clear chat", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

        st.divider()
        st.caption("Try an example")
        for index, example in enumerate(EXAMPLE_QUESTIONS):
            if st.button(example, key=f"example_{index}", use_container_width=True):
                st.session_state.pending_question = example

    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "live_search_times" not in st.session_state:
        st.session_state.live_search_times = []

    for saved_message in st.session_state.messages:
        render_message(saved_message)

    prompt = st.chat_input("Ask about DarGlobal or Wasalt")
    if not prompt:
        prompt = st.session_state.pop("pending_question", None)
    else:
        st.session_state.pop("pending_question", None)
    if not prompt:
        return

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    answer = ""
    sources: list[dict[str, str]] = []
    notice = ""
    with st.chat_message("assistant"):
        st.caption(f"Answered using {mode}")
        with st.spinner("Finding an answer..."):
            try:
                context = ""
                history = st.session_state.messages[-9:-1]
                if mode == "Knowledge Base":
                    chunks = search_chunks(
                        prompt,
                        db_path=ROOT / "data" / "knowledge.db",
                        limit=5,
                    )
                    context = format_chunks(chunks)
                    sources = [
                        {"title": chunk.title, "url": chunk.url, "source": chunk.source}
                        for chunk in chunks
                    ]
                else:
                    result = search_live(
                        prompt,
                        api_key=get_setting("SERPER_API_KEY"),
                        recent_searches=st.session_state.live_search_times,
                    )
                    context = result.context
                    notice = result.message
                    sources = [
                        {"title": source.title, "url": source.url, "source": source.title}
                        for source in result.sources
                    ]

                answer = answer_question(
                    prompt,
                    context,
                    history,
                    api_key=get_setting("OPENROUTER_API_KEY"),
                    model=get_setting("OPENROUTER_MODEL", "openai/gpt-oss-20b:free"),
                    fallback_models=get_setting("OPENROUTER_FALLBACK_MODELS"),
                )
            except (RuntimeError, OSError, ValueError) as exc:
                answer = f"Sorry, I couldn't complete that request: {exc}"
        st.markdown(answer)
        if notice:
            st.info(notice)
        if sources:
            with st.expander("Sources"):
                for source in sources:
                    title = source.get("title") or "Source"
                    url = source.get("url", "")
                    st.markdown(f"- [{title}]({url})" if url else f"- {title}")

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": answer,
            "notice": notice,
            "sources": sources,
            "mode": mode,
            "created_at": time.time(),
        }
    )


if __name__ == "__main__":
    main()
