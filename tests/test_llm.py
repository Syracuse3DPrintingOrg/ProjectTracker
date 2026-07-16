import pytest

from app.services import llm


def test_parse_plain_json():
    assert llm.parse_json_response('{"a": 1}') == {"a": 1}
    assert llm.parse_json_response("[1, 2]") == [1, 2]


def test_parse_fenced_json():
    text = 'Here you go:\n```json\n{"a": 1}\n```\nEnjoy.'
    assert llm.parse_json_response(text) == {"a": 1}
    assert llm.parse_json_response("```\n[1]\n```") == [1]


def test_parse_json_embedded_in_prose():
    text = 'Sure! The subtasks are ["one", "two"] as requested.'
    assert llm.parse_json_response(text) == ["one", "two"]


def test_parse_no_json_raises():
    with pytest.raises(llm.LLMError):
        llm.parse_json_response("I cannot help with that.")


def test_suggest_subtasks_parses_and_caps(monkeypatch):
    reply = "```json\n" + str([f"task {i}" for i in range(20)]).replace("'", '"') + "\n```"
    monkeypatch.setattr(llm, "complete", lambda prompt, settings=None: reply)
    items = llm.suggest_subtasks("Big card")
    assert len(items) == 12
    assert items[0] == "task 0"


def test_draft_description_requires_shape(monkeypatch):
    monkeypatch.setattr(llm, "complete", lambda prompt, settings=None: '["not a dict"]')
    with pytest.raises(llm.LLMError):
        llm.draft_description("Card")
    monkeypatch.setattr(
        llm, "complete", lambda prompt, settings=None: '{"description": "Do the thing."}'
    )
    assert llm.draft_description("Card") == "Do the thing."


def test_is_configured(monkeypatch):
    assert llm.is_configured({"llm_provider": "gemini", "gemini_api_key": ""}) is False
    assert llm.is_configured({"llm_provider": "gemini", "gemini_api_key": "k"}) is True
    assert llm.is_configured({"llm_provider": "ollama", "ollama_url": "http://x"}) is True
    assert (
        llm.is_configured({"llm_provider": "anthropic", "anthropic_api_key": "k"})
        is True
    )
