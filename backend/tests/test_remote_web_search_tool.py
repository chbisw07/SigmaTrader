from __future__ import annotations

from app.services.ai_toolcalling.openai_toolcaller import (
    _build_openai_responses_body,
    _parse_openai_responses_payload,
)


def test_responses_body_no_web_search_has_no_tools() -> None:
    body = _build_openai_responses_body(
        model="gpt-test",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=123,
        temperature=0.2,
        enable_web_search=False,
        web_search_allowed_domains=None,
        web_search_external_web_access=True,
        web_search_include_sources=True,
        force_json_object=False,
    )
    assert body["model"] == "gpt-test"
    assert body["input"] == [{"role": "user", "content": "hi"}]
    assert body["max_output_tokens"] == 123
    assert "tools" not in body
    assert "tool_choice" not in body
    assert "include" not in body


def test_responses_body_web_search_respects_domains_and_live_access_and_sources() -> None:
    body = _build_openai_responses_body(
        model="gpt-test",
        messages=[{"role": "system", "content": "json only"}, {"role": "user", "content": "news"}],
        max_tokens=321,
        temperature=None,
        enable_web_search=True,
        web_search_allowed_domains=["reuters.com", " bloomberg.com ", ""],
        web_search_external_web_access=False,
        web_search_include_sources=True,
        # Force JSON mode is ignored when web_search is enabled (OpenAI restriction).
        force_json_object=True,
    )
    assert body["max_output_tokens"] == 321
    assert "text" not in body
    assert body["tool_choice"] == "auto"
    assert body["include"] == ["web_search_call.action.sources"]
    assert isinstance(body["tools"], list) and len(body["tools"]) == 1
    tool = body["tools"][0]
    assert tool["type"] == "web_search"
    assert tool["external_web_access"] is False
    assert tool["filters"]["allowed_domains"] == ["reuters.com", "bloomberg.com"]


def test_responses_parser_handles_sources_and_domains_only() -> None:
    payload = {
        "id": "resp_123",
        "output_text": '{"final_message":"ok"}',
        "usage": {"input_tokens": 1, "output_tokens": 2},
        "output": [
            {
                "type": "web_search_call",
                "action": {
                    "sources": [
                        {"url": "https://www.reuters.com/world/foo"},
                        {"url": "https://example.com/a?b=c"},
                        {"url": "https://www.reuters.com/other"},
                    ]
                },
            }
        ],
    }
    text, meta = _parse_openai_responses_payload(payload)
    assert text == '{"final_message":"ok"}'
    assert meta["id"] == "resp_123"
    assert meta["usage"] == {"input_tokens": 1, "output_tokens": 2}
    assert meta["web_search"]["calls"] == 1
    # Must be domains only (no paths).
    assert meta["web_search"]["source_domains"] == ["reuters.com", "example.com"]


def test_responses_parser_works_without_output_text_or_sources() -> None:
    payload = {
        "id": "resp_456",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": '{"final_message":"hi"}'}],
            }
        ],
    }
    text, meta = _parse_openai_responses_payload(payload)
    assert text == '{"final_message":"hi"}'
    assert meta["id"] == "resp_456"
    assert "web_search" not in meta
