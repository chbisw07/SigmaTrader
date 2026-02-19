from __future__ import annotations

from app.services.ai_toolcalling.policy import classify_tool
from app.services.ai_toolcalling.redaction import redact_for_llm


def test_redact_for_llm_masks_sensitive_keys() -> None:
    payload = {
        "api_key": "sk-THISISAVERYLONGSECRETKEYVALUE1234",
        "access_token": "ya29.A0ARrdaM-THISLOOKSLIKEAGOOGLETOKEN",
        "session_id": "36e0bfee-753f-4dbc-b650-006524030df9%7C...",
        "user_id": "CZC754",
        "order_id": "241219001234567",
        "nested": {"refresh_token": "r1-abcdef", "ok": 1},
        "list": [{"password": "p@ssw0rd", "qty": 2}],
    }

    red = redact_for_llm(payload)

    assert red["api_key"] != payload["api_key"]
    assert str(red["api_key"]).startswith("sk")  # masked, but provider prefix preserved
    assert red["access_token"] != payload["access_token"]
    assert red["session_id"] != payload["session_id"]
    assert red["user_id"] != payload["user_id"]
    assert red["order_id"] != payload["order_id"]
    assert red["nested"]["refresh_token"] != payload["nested"]["refresh_token"]
    assert red["nested"]["ok"] == 1
    assert red["list"][0]["password"] != payload["list"][0]["password"]
    assert red["list"][0]["qty"] == 2


def test_classify_tool_blocks_profile() -> None:
    assert classify_tool("get_profile") != "read"
