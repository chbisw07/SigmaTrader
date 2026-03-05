from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List

import httpx
from urllib.parse import urlparse


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


def _safe_domain(url: str) -> str:
    """Extract a safe domain label from a URL (no path/query); best-effort."""

    try:
        p = urlparse(str(url or "").strip())
        host = (p.hostname or "").strip().lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


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


def _build_openai_responses_body(
    *,
    model: str,
    messages: List[Dict[str, Any]],
    max_tokens: int | None,
    temperature: float | None,
    enable_web_search: bool,
    web_search_allowed_domains: list[str] | None,
    web_search_external_web_access: bool,
    web_search_include_sources: bool,
    force_json_object: bool,
) -> dict[str, Any]:
    body: dict[str, Any] = {"model": model, "input": messages}
    if temperature is not None:
        body["temperature"] = float(temperature)
    if max_tokens is not None:
        # Responses API uses max_output_tokens (not chat-completions max_tokens).
        body["max_output_tokens"] = int(max_tokens)
    if force_json_object:
        # Keep the hybrid reasoner contract stable: a single JSON object output.
        body["text"] = {"format": {"type": "json_object"}}

    if enable_web_search:
        tool: dict[str, Any] = {"type": "web_search", "external_web_access": bool(web_search_external_web_access)}
        if web_search_allowed_domains:
            allowed = [d.strip().lower() for d in web_search_allowed_domains if str(d or "").strip()]
            if allowed:
                tool["filters"] = {"allowed_domains": allowed}
        body["tools"] = [tool]
        body["tool_choice"] = "auto"
        if web_search_include_sources:
            # Request sources via include mechanism (kept out of the main assistant text).
            body["include"] = ["web_search_call.action.sources"]

    return body


def _parse_openai_responses_payload(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    # Prefer the server-provided convenience field.
    out_text = payload.get("output_text")
    if isinstance(out_text, str):
        text = out_text
    else:
        text_parts: list[str] = []
        out = payload.get("output")
        if isinstance(out, list):
            for item in out:
                if not isinstance(item, dict):
                    continue
                if str(item.get("type") or "") != "message":
                    continue
                if str(item.get("role") or "") != "assistant":
                    continue
                content = item.get("content")
                if isinstance(content, list):
                    for part in content:
                        if not isinstance(part, dict):
                            continue
                        ptype = str(part.get("type") or "")
                        if ptype not in {"output_text", "text"}:
                            continue
                        t = part.get("text")
                        if isinstance(t, str) and t:
                            text_parts.append(t)
        text = "".join(text_parts)

    # Extract web_search tool usage indicators without storing full URLs.
    web_search_calls = 0
    source_domains: list[str] = []
    out = payload.get("output")
    if isinstance(out, list):
        seen: set[str] = set()
        for item in out:
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "") != "web_search_call":
                continue
            web_search_calls += 1
            action = item.get("action")
            if not isinstance(action, dict):
                continue
            sources = action.get("sources")
            if not isinstance(sources, list):
                continue
            for s in sources:
                if not isinstance(s, dict):
                    continue
                url = s.get("url")
                if not isinstance(url, str) or not url.strip():
                    continue
                d = _safe_domain(url)
                if d and d not in seen:
                    seen.add(d)
                    source_domains.append(d)

    meta: dict[str, Any] = {
        "id": payload.get("id"),
        "usage": payload.get("usage"),
    }
    if web_search_calls:
        meta["web_search"] = {"calls": int(web_search_calls), "source_domains": source_domains[:25]}
    return text, meta


async def openai_responses_plain(
    *,
    api_key: str | None,
    model: str,
    messages: List[Dict[str, Any]],
    base_url: str = "https://api.openai.com/v1",
    timeout_seconds: float = 30,
    max_tokens: int | None = None,
    temperature: float | None = None,
    enable_web_search: bool = False,
    web_search_allowed_domains: list[str] | None = None,
    web_search_external_web_access: bool = True,
    web_search_include_sources: bool = True,
    force_json_object: bool = False,
) -> OpenAiAssistantTurn:
    """OpenAI Responses API request (optionally with web_search tool).

    Used only when explicitly enabled via configuration to preserve default behavior.
    """

    url = f"{base_url.rstrip('/')}/responses"
    body = _build_openai_responses_body(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        enable_web_search=enable_web_search,
        web_search_allowed_domains=web_search_allowed_domains,
        web_search_external_web_access=web_search_external_web_access,
        web_search_include_sources=web_search_include_sources,
        force_json_object=force_json_object,
    )
    headers: dict[str, str] = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
            resp = await client.post(url, headers=headers, json=body)
    except httpx.TimeoutException as exc:
        raise OpenAiChatError(f"LLM endpoint timed out after {timeout_seconds:.0f}s.") from exc
    except httpx.RequestError as exc:
        raise OpenAiChatError(f"LLM endpoint request failed: {type(exc).__name__}: {exc}") from exc
    except Exception as exc:
        raise OpenAiChatError(str(exc) or "LLM endpoint request failed.") from exc
    latency_ms = int((time.perf_counter() - t0) * 1000)

    if resp.status_code in {401, 403}:
        raise OpenAiChatError("LLM endpoint unauthorized (check API key).")
    if resp.status_code >= 400:
        raise OpenAiChatError(f"LLM endpoint HTTP {resp.status_code}: {resp.text}")

    try:
        payload = resp.json()
    except Exception as exc:
        preview = (resp.text or "")[:500]
        raise OpenAiChatError(f"LLM endpoint returned non-JSON response. status={resp.status_code} body={preview!r}") from exc
    if not isinstance(payload, dict):
        raise OpenAiChatError("Invalid OpenAI response.")

    content, parsed_meta = _parse_openai_responses_payload(payload)
    raw_meta: dict[str, Any] = {"latency_ms": latency_ms, **parsed_meta}
    return OpenAiAssistantTurn(content=content, tool_calls=[], raw=raw_meta)


async def openai_chat_with_tools(
    *,
    api_key: str | None,
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
    headers: dict[str, str] = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
            resp = await client.post(url, headers=headers, json=body)
    except httpx.TimeoutException as exc:
        raise OpenAiChatError(f"LLM endpoint timed out after {timeout_seconds:.0f}s.") from exc
    except httpx.RequestError as exc:
        raise OpenAiChatError(f"LLM endpoint request failed: {type(exc).__name__}: {exc}") from exc
    except Exception as exc:
        raise OpenAiChatError(str(exc) or "LLM endpoint request failed.") from exc
    latency_ms = int((time.perf_counter() - t0) * 1000)

    if resp.status_code in {401, 403}:
        raise OpenAiChatError("LLM endpoint unauthorized (check API key).")
    if resp.status_code >= 400:
        raise OpenAiChatError(f"LLM endpoint HTTP {resp.status_code}: {resp.text}")

    try:
        payload = resp.json()
    except Exception as exc:
        preview = (resp.text or "")[:500]
        raise OpenAiChatError(f"LLM endpoint returned non-JSON response. status={resp.status_code} body={preview!r}") from exc
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


async def openai_chat_plain(
    *,
    api_key: str | None,
    model: str,
    messages: List[Dict[str, Any]],
    base_url: str = "https://api.openai.com/v1",
    timeout_seconds: float = 30,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> OpenAiAssistantTurn:
    """OpenAI-compatible chat completion without tools.

    Used by the Hybrid LLM gateway where the remote reasoner emits ToolRequests
    as JSON instead of OpenAI tool-calls.
    """
    url = f"{base_url.rstrip('/')}/chat/completions"
    body: Dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    if temperature is not None:
        body["temperature"] = float(temperature)
    if max_tokens is not None:
        body["max_tokens"] = int(max_tokens)
    headers: dict[str, str] = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
            resp = await client.post(url, headers=headers, json=body)
    except httpx.TimeoutException as exc:
        raise OpenAiChatError(f"LLM endpoint timed out after {timeout_seconds:.0f}s.") from exc
    except httpx.RequestError as exc:
        raise OpenAiChatError(f"LLM endpoint request failed: {type(exc).__name__}: {exc}") from exc
    except Exception as exc:
        raise OpenAiChatError(str(exc) or "LLM endpoint request failed.") from exc
    latency_ms = int((time.perf_counter() - t0) * 1000)

    if resp.status_code in {401, 403}:
        raise OpenAiChatError("LLM endpoint unauthorized (check API key).")
    if resp.status_code >= 400:
        raise OpenAiChatError(f"LLM endpoint HTTP {resp.status_code}: {resp.text}")

    try:
        payload = resp.json()
    except Exception as exc:
        preview = (resp.text or "")[:500]
        raise OpenAiChatError(f"LLM endpoint returned non-JSON response. status={resp.status_code} body={preview!r}") from exc
    if not isinstance(payload, dict):
        raise OpenAiChatError("Invalid OpenAI response.")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise OpenAiChatError("OpenAI returned no choices.")
    msg = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(msg, dict):
        raise OpenAiChatError("OpenAI response missing message.")

    content = str(msg.get("content") or "")
    raw_meta = {"latency_ms": latency_ms, "usage": payload.get("usage"), "id": payload.get("id")}
    return OpenAiAssistantTurn(content=content, tool_calls=[], raw=raw_meta)


__all__ = [
    "OpenAiAssistantTurn",
    "OpenAiChatError",
    "OpenAiToolCall",
    "openai_chat_plain",
    "openai_responses_plain",
    "openai_chat_with_tools",
]
