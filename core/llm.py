"""OpenRouter chat-completion client with model fallback support."""

from __future__ import annotations

from typing import Iterable, Mapping

import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
SYSTEM_PROMPT = (
    "For greetings, pleasantries, or brief social messages, respond naturally and politely even "
    "if the context is empty. Only answer questions related to DarGlobal or Wasalt. If a question "
    "is unrelated to these companies, politely decline and invite the user to ask about DarGlobal "
    "or Wasalt instead. For relevant factual questions, answer only from the provided context; if "
    "the answer is not there, say you don't know. Be concise, mention source names where useful, "
    "and do not invent figures."
)


def answer_question(
    question: str,
    context: str,
    history: Iterable[Mapping[str, str]],
    *,
    api_key: str,
    model: str,
    fallback_models: str = "",
) -> str:
    """Ask OpenRouter using the selected model followed by configured fallbacks."""
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured.")

    models = list(dict.fromkeys([model, *[item.strip() for item in fallback_models.split(",") if item.strip()]]))
    if not models:
        raise RuntimeError("No OpenRouter model is configured.")
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in history:
        role = turn.get("role")
        content = turn.get("content")
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append(
        {
            "role": "user",
            "content": f"Context:\n{context}\n\nQuestion: {question}",
        }
    )

    last_error = "OpenRouter returned an empty response."
    for selected_model in models:
        try:
            response = requests.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "http://localhost",
                    "X-Title": "DarGlobal and Wasalt Assistant",
                },
                json={
                    "model": selected_model,
                    "messages": messages,
                    "temperature": 0.2,
                },
                timeout=40,
            )
        except requests.RequestException as exc:
            last_error = f"OpenRouter request failed: {exc}"
            continue

        if response.status_code == 429 or response.status_code >= 500:
            last_error = f"OpenRouter model {selected_model} returned HTTP {response.status_code}."
            continue
        try:
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            if isinstance(content, str) and content.strip():
                return content.strip()
            last_error = f"OpenRouter model {selected_model} returned an empty response."
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
            last_error = f"OpenRouter response from {selected_model} was invalid: {exc}"

    raise RuntimeError(f"All configured OpenRouter models failed. {last_error}")
