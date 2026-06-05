from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
        text = payload.get("text")
        if text is None:
            text = payload.get("reply")
        if text is None:
            text = ""
        emotion = payload.get("emotion", "")
        return AgentReply(
            text=str(text),
            emotion=str(emotion),
            display_text=payload.get("display_text"),
            duration_ms=payload.get("duration_ms"),
            intensity=payload.get("intensity"),
        )
    return AgentReply(text=str(payload))


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
