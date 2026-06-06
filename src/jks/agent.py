from __future__ import annotations

from dataclasses import dataclass
import json
import os
import shlex
import subprocess
from typing import Any, Iterable
from urllib.parse import urlsplit

import requests


@dataclass(frozen=True)
class AgentReply:
    text: str
    emotion: str = ""
    display_text: Any = None
    duration_ms: Any = None
    intensity: Any = None


class AgentProviderError(RuntimeError):
    """Raised when the remote agent transport or response contract fails."""


def parse_agent_reply(payload: Any) -> AgentReply:
    if isinstance(payload, str):
        structured = _parse_json_object(payload)
        if structured is not None:
            return parse_agent_reply(structured)
        return AgentReply(text=payload)
    if isinstance(payload, dict):
        normalized = _unwrap_envelope(payload)
        structured = _extract_structured_content(normalized)
        if structured is not None:
            normalized = structured
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


def _parse_json_object(value: str) -> dict[str, Any] | None:
    stripped = value.strip()
    if not stripped.startswith("{") or not stripped.endswith("}"):
        return None
    try:
        parsed = json.loads(stripped)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _extract_structured_content(payload: dict[str, Any]) -> dict[str, Any] | None:
    content = _assistant_content(payload)
    if not isinstance(content, str):
        return None
    parsed = _parse_json_object(content)
    if parsed is None:
        return None
    if _first_present(parsed, ("text", "reply", "message", "content")) is None:
        return None
    return parsed


def _assistant_content(payload: dict[str, Any]) -> Any:
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first_choice = choices[0]
        if isinstance(first_choice, dict):
            message = first_choice.get("message")
            if isinstance(message, dict):
                return message.get("content")
            if first_choice.get("text") is not None:
                return first_choice.get("text")

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
            return selected.get("content")

    direct = _first_present(payload, ("message", "content"))
    if isinstance(direct, dict):
        return direct.get("content")
    return direct


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
    def __init__(
        self,
        endpoint: str,
        token: str = "",
        timeout: float = 30.0,
        model: str = "hermes-agent",
    ):
        self.endpoint = endpoint
        self.token = token
        self.timeout = timeout
        self.model = model or "hermes-agent"

    def send_message(self, text: str, conversation_id: str) -> AgentReply:
        if not self.endpoint:
            raise RuntimeError("JKS_AGENT_ENDPOINT is not configured")

        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if _uses_openai_chat_completions(self.endpoint):
            body = {
                "model": self.model,
                "messages": [{"role": "user", "content": text}],
                "stream": False,
            }
            if conversation_id:
                headers["X-Hermes-Session-Id"] = conversation_id
        else:
            body = {"message": text, "conversation_id": conversation_id}

        try:
            response = requests.post(
                self.endpoint,
                json=body,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except Exception as exc:
            raise AgentProviderError("agent request failed") from exc

        try:
            payload = response.json()
        except ValueError:
            payload = response.text
        reply = parse_agent_reply(payload)
        if not reply.text.strip():
            raise AgentProviderError("agent response did not contain text")
        return reply

    def probe_contract(self) -> AgentReply:
        return self.send_message("JKS contract probe", "contract-probe")


class SshHermesAgentClient:
    def __init__(
        self,
        host: str,
        user: str = "root",
        password: str = "",
        command: str = "/usr/local/lib/hermes-agent/venv/bin/hermes",
        workdir: str = "/usr/local/lib/hermes-agent",
        timeout: float = 120.0,
        model: str = "",
    ):
        self.host = host
        self.user = user or ""
        self.password = password
        self.command = command or "/usr/local/lib/hermes-agent/venv/bin/hermes"
        self.workdir = workdir or "/usr/local/lib/hermes-agent"
        self.timeout = timeout
        self.model = model

    def send_message(self, text: str, conversation_id: str) -> AgentReply:
        if not self.host:
            raise RuntimeError("JKS_AGENT_HOST is not configured")

        target = f"{self.user}@{self.host}" if self.user else self.host
        session_name = _ssh_session_name(conversation_id)
        prompt = _voice_json_prompt(text)
        hermes_args = [self.command, "--continue", session_name]
        if self.model and self.model != "hermes-agent":
            hermes_args.extend(["--model", self.model])
        hermes_args.extend(["-z", prompt])
        remote_command = f"cd {shlex.quote(self.workdir)} && {shlex.join(hermes_args)}"
        ssh_command = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "ConnectTimeout=10",
            target,
            remote_command,
        ]
        command = ssh_command
        env = os.environ.copy()
        if self.password:
            command = ["sshpass", "-e", *ssh_command]
            env["SSHPASS"] = self.password
        else:
            env.pop("SSHPASS", None)

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,
                timeout=self.timeout,
                env=env,
            )
        except Exception as exc:
            raise AgentProviderError("hermes ssh request failed") from exc

        reply = parse_agent_reply(completed.stdout.strip())
        if not reply.text.strip():
            raise AgentProviderError("agent response did not contain text")
        return reply

    def probe_contract(self) -> AgentReply:
        return self.send_message("JKS contract probe", "contract-probe")


def _uses_openai_chat_completions(endpoint: str) -> bool:
    try:
        path = urlsplit(endpoint).path.rstrip("/")
    except ValueError:
        return False
    return path.endswith("/v1/chat/completions")


def build_agent_client(config, timeout: float = 30.0):
    endpoint = getattr(config, "agent_endpoint", "")
    if endpoint and not _is_placeholder(endpoint):
        return HttpAgentClient(
            endpoint,
            getattr(config, "agent_token", ""),
            timeout=timeout,
            model=getattr(config, "agent_model", "hermes-agent"),
        )
    host = getattr(config, "agent_host", "")
    if host and not _is_placeholder(host):
        return SshHermesAgentClient(
            host=host,
            user=getattr(config, "agent_user", "") or "root",
            password=getattr(config, "agent_ssh_password", ""),
            command=getattr(config, "agent_command", ""),
            workdir=getattr(config, "agent_workdir", ""),
            timeout=timeout,
            model=getattr(config, "agent_model", ""),
        )
    return HttpAgentClient(
        endpoint,
        getattr(config, "agent_token", ""),
        timeout=timeout,
        model=getattr(config, "agent_model", "hermes-agent"),
    )


def _is_placeholder(value: str) -> bool:
    return value.strip().lower().startswith("replace-with-")


def _ssh_session_name(conversation_id: str) -> str:
    safe = []
    for char in conversation_id:
        safe.append(char if char.isalnum() or char in {"-", "_"} else "-")
    value = "".join(safe).strip("-_")[:80]
    return f"jks-{value or 'session'}"


def _voice_json_prompt(text: str) -> str:
    return (
        "JKS voice call turn. Return only compact JSON with keys text, emotion, "
        "display_text, duration_ms, intensity. emotion must be one of neutral, "
        "happy, thinking, speaking, listening, surprised, sleepy, sad, angry, error. "
        "display_text must be a short ASCII OLED label. Do not include markdown. "
        f"User said: {text}"
    )
