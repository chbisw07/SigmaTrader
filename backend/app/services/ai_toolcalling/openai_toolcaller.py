from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List

import httpx


@dataclass(frozen=True)
class OpenAiToolCall:
    tool_call_id: str
    name: str
    arguments: Dict[str, Any]


@dataclass(frozen=True)
class OpenAiAssistantTurn:
    content: str
    tool_calls: List[OpenAiToolCall]
    raw: Dict[str, Any]


class OpenAiChatError(RuntimeError):
    pass


def _parse_tool_calls(msg: dict[str, Any]) -> List[OpenAiToolCall]:
    rows = msg.get("tool_calls")
    if not isinstance(rows, list):
        return []
    out: List[OpenAiToolCall] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        tc_id = str(r.get("id") or "").strip()
        fn = r.get("function") if isinstance(r.get("function"), dict) else {}
        name = str(fn.get("name") or "").strip()
        args_raw = fn.get("arguments")
        args: Dict[str, Any] = {}
        if isinstance(args_raw, str) and args_raw.strip():
            try:
                parsed = json.loads(args_raw)
                if isinstance(parsed, dict):
                    args = parsed
            except Exception:
                args = {}
        if tc_id and name:
            out.append(OpenAiToolCall(tool_call_id=tc_id, name=name, arguments=args))
    return out


async def openai_chat_with_tools(
    *,
    api_key: str,
    model: str,
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    base_url: str = "https://api.openai.com/v1",
    timeout_seconds: float = 30,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> OpenAiAssistantTurn:
    url = f"{base_url.rstrip('/')}/chat/completions"
    body: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
    }
    if temperature is not None:
        body["temperature"] = float(temperature)
    if max_tokens is not None:
        body["max_tokens"] = int(max_tokens)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
        resp = await client.post(url, headers=headers, json=body)
    latency_ms = int((time.perf_counter() - t0) * 1000)

    if resp.status_code in {401, 403}:
        raise OpenAiChatError("OpenAI unauthorized (check API key).")
    if resp.status_code >= 400:
        raise OpenAiChatError(f"OpenAI HTTP {resp.status_code}: {resp.text}")

    payload = resp.json()
    if not isinstance(payload, dict):
        raise OpenAiChatError("Invalid OpenAI response.")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise OpenAiChatError("OpenAI returned no choices.")
    msg = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(msg, dict):
        raise OpenAiChatError("OpenAI response missing message.")

    content = str(msg.get("content") or "")
    tool_calls = _parse_tool_calls(msg)
    raw_meta = {"latency_ms": latency_ms, "usage": payload.get("usage"), "id": payload.get("id")}
    return OpenAiAssistantTurn(content=content, tool_calls=tool_calls, raw=raw_meta)


__all__ = ["OpenAiAssistantTurn", "OpenAiChatError", "OpenAiToolCall", "openai_chat_with_tools"]
