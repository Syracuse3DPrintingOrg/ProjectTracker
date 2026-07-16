"""LLM assist. Gemini by default; Anthropic, OpenAI, and Ollama also work.

Every provider is called over plain HTTP with httpx, no SDKs. Replies are
expected as JSON but may arrive fenced in markdown; parse_json_response
handles both.
"""

import json
import re

import httpx

from .. import config

TIMEOUT = 60.0


class LLMError(Exception):
    pass


def parse_json_response(text: str):
    """Parse a JSON reply that may be wrapped in ``` fences or prose."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except ValueError:
        start = min(
            (i for i in (text.find("{"), text.find("[")) if i != -1), default=-1
        )
        if start == -1:
            raise LLMError(f"no JSON in reply: {text[:200]}")
        depth = 0
        opener = text[start]
        closer = "}" if opener == "{" else "]"
        for i in range(start, len(text)):
            if text[i] == opener:
                depth += 1
            elif text[i] == closer:
                depth -= 1
                if depth == 0:
                    return json.loads(text[start : i + 1])
        raise LLMError(f"unbalanced JSON in reply: {text[:200]}")


def is_configured(settings: dict | None = None) -> bool:
    s = settings or config.load_settings()
    provider = s.get("llm_provider", "gemini")
    if provider == "ollama":
        return bool(s.get("ollama_url"))
    return bool(s.get(f"{provider}_api_key"))


def complete(prompt: str, settings: dict | None = None) -> str:
    """Send one prompt, return the raw text reply."""
    s = settings or config.load_settings()
    provider = s.get("llm_provider", "gemini")
    model = s.get("llm_model") or config.default_model(provider)
    try:
        if provider == "gemini":
            return _gemini(prompt, s["gemini_api_key"], model)
        if provider == "anthropic":
            return _anthropic(prompt, s["anthropic_api_key"], model)
        if provider == "openai":
            return _openai(prompt, s["openai_api_key"], model)
        if provider == "ollama":
            return _ollama(prompt, s["ollama_url"], model)
    except httpx.HTTPStatusError as exc:
        raise LLMError(
            f"{provider} returned {exc.response.status_code}:"
            f" {exc.response.text[:300]}"
        )
    except httpx.HTTPError as exc:
        raise LLMError(f"{provider} request failed: {exc}")
    raise LLMError(f"unknown provider: {provider}")


def _gemini(prompt: str, api_key: str, model: str) -> str:
    if not api_key:
        raise LLMError("Gemini API key is not set")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    resp = httpx.post(
        url,
        headers={"x-goog-api-key": api_key},
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise LLMError(f"unexpected Gemini reply: {json.dumps(data)[:300]}")


def _anthropic(prompt: str, api_key: str, model: str) -> str:
    if not api_key:
        raise LLMError("Anthropic API key is not set")
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        json={
            "model": model,
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    try:
        return "".join(
            block["text"] for block in data["content"] if block["type"] == "text"
        )
    except (KeyError, TypeError):
        raise LLMError(f"unexpected Anthropic reply: {json.dumps(data)[:300]}")


def _openai(prompt: str, api_key: str, model: str) -> str:
    if not api_key:
        raise LLMError("OpenAI API key is not set")
    resp = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise LLMError(f"unexpected OpenAI reply: {json.dumps(data)[:300]}")


def _ollama(prompt: str, base_url: str, model: str) -> str:
    resp = httpx.post(
        f"{base_url.rstrip('/')}/api/generate",
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=120.0,
    )
    resp.raise_for_status()
    data = resp.json()
    if "response" not in data:
        raise LLMError(f"unexpected Ollama reply: {json.dumps(data)[:300]}")
    return data["response"]


# ---- assist actions ----

SUBTASKS_PROMPT = """You are helping plan work on a project board card.
Card title: {title}
Card description: {description}

Break this card into 3 to 8 concrete subtasks. Reply with ONLY a JSON array
of short subtask strings, no commentary.
"""

DESCRIBE_PROMPT = """You are helping write a project board card.
Card title: {title}
Current description (may be empty): {description}

Write a clear, concise description for this card: what needs to happen and
what done looks like. Two short paragraphs at most, plain text, no headings.
Reply with ONLY a JSON object: {{"description": "..."}}
"""


def suggest_subtasks(title: str, description: str = "") -> list[str]:
    reply = complete(SUBTASKS_PROMPT.format(title=title, description=description))
    items = parse_json_response(reply)
    if not isinstance(items, list):
        raise LLMError("expected a JSON array of subtasks")
    return [str(i) for i in items][:12]


def draft_description(title: str, description: str = "") -> str:
    reply = complete(DESCRIBE_PROMPT.format(title=title, description=description))
    data = parse_json_response(reply)
    if not isinstance(data, dict) or "description" not in data:
        raise LLMError("expected a JSON object with a description")
    return str(data["description"])
