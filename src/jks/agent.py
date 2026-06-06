from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import requests


@dataclass(frozen=True)
class AgentReply:
    text: str
    emotion: str = ""
    display_text: Any = None
    duration_ms: Any = None
    intensity: Any = None


def parse_agent_reply(payload: Any) -> AgentReply:
    if isinstance(payload, str):
        return AgentReply(text=payload)
    if isinstance(payload, dict):
        normalized = _unwrap_envelope(payload)
        text = _extract_text(normalized, allow_legacy_dict_stringify=normalized is payload)
        display_fields = _extract_display_fields(payload)
        if normalized is not payload:
            display_fields.update(
                {
                    key: value
                    for key, value in _extract_display_fields(normalized).items()
                    if value is not None and value != ""
                }
            )
        emotion = display_fields.get("emotion", "")
        return AgentReply(
            text=text,
            emotion=str(emotion),
            display_text=display_fields.get("display_text"),
            duration_ms=display_fields.get("duration_ms"),
            intensity=display_fields.get("intensity"),
        )
    return AgentReply(text=str(payload))


def _first_present(mapping: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _content_to_text(content: Any, allow_dict_stringify: bool = False) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                item_type = item.get("type")
                if item_type in {"text", "output_text"} and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif item_type in {"text", "output_text"} and isinstance(item.get("content"), str):
                    parts.append(item["content"])
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts)
    if isinstance(content, dict):
        if allow_dict_stringify:
            return str(content)
        nested = _first_present(content, ("text", "content", "message"))
        if nested is not None:
            return _content_to_text(nested)
        return ""
    return str(content)


def _extract_display_fields(payload: dict[str, Any]) -> dict[str, Any]:
    display = {}
    nested = _first_present(payload, ("display", "display_intent", "expression"))
    if isinstance(nested, dict):
        display.update(
            {
                "emotion": nested.get("emotion", nested.get("name", "")),
                "display_text": nested.get("display_text", nested.get("text")),
                "duration_ms": nested.get("duration_ms"),
                "intensity": nested.get("intensity"),
            }
        )

    display.update(
        {
            "emotion": payload.get("emotion", display.get("emotion", "")),
            "display_text": payload.get("display_text", display.get("display_text")),
            "duration_ms": payload.get("duration_ms", display.get("duration_ms")),
            "intensity": payload.get("intensity", display.get("intensity")),
        }
    )
    return display


def _unwrap_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    current = payload
    for _ in range(4):
        direct_value = _first_present(
            current,
            (
                "text",
                "reply",
                "message",
                "content",
                "choices",
                "messages",
            ),
        )
        if direct_value is not None:
            return current

        nested = _first_present(current, ("result", "data", "output", "response"))
        if not isinstance(nested, dict):
            return current
        current = nested
    return current


def _extract_text(payload: dict[str, Any], allow_legacy_dict_stringify: bool = False) -> str:
    legacy_direct = _first_present(payload, ("text", "reply"))
    if legacy_direct is not None:
        return _content_to_text(
            legacy_direct,
            allow_dict_stringify=allow_legacy_dict_stringify,
        )

    direct = _first_present(payload, ("message", "content"))
    if direct is not None:
        text = _content_to_text(direct)
        if text:
            return text

    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first_choice = choices[0]
        if isinstance(first_choice, dict):
            if first_choice.get("text") is not None:
                return _content_to_text(first_choice.get("text"))
            message = first_choice.get("message")
            if isinstance(message, dict):
                return _content_to_text(message.get("content"))

    messages = payload.get("messages")
    if isinstance(messages, list) and messages:
        selected = None
        for message in messages:
            if isinstance(message, dict) and message.get("role") == "assistant":
                selected = message
        if selected is None:
            for message in reversed(messages):
                if isinstance(message, dict):
                    selected = message
                    break
        if isinstance(selected, dict):
            return _content_to_text(selected.get("content"))

    return ""


class HttpAgentClient:
    def __init__(self, endpoint: str, token: str = "", timeout: float = 30.0):
        self.endpoint = endpoint
        self.token = token
        self.timeout = timeout

    def send_message(self, text: str, conversation_id: str) -> AgentReply:
        if not self.endpoint:
            raise RuntimeError("JKS_AGENT_ENDPOINT is not configured")

        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        response = requests.post(
            self.endpoint,
            json={"message": text, "conversation_id": conversation_id},
            headers=headers,
            timeout=self.timeout,
        )
        response.raise_for_status()

        try:
            payload = response.json()
        except ValueError:
            payload = response.text
        return parse_agent_reply(payload)
