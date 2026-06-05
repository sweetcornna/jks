from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class AppConfig:
    agent_host: str
    agent_user: str
    agent_auth_method: str
    agent_endpoint: str
    agent_token: str
    stt_provider: str
    stt_endpoint: str
    tts_provider: str
    tts_endpoint: str
    tts_voice: str
    oled_port: str
    oled_baud: int


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default

    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def load_config() -> AppConfig:
    return AppConfig(
        agent_host=os.environ.get("JKS_AGENT_HOST", ""),
        agent_user=os.environ.get("JKS_AGENT_USER", ""),
        agent_auth_method=os.environ.get("JKS_AGENT_AUTH_METHOD", ""),
        agent_endpoint=os.environ.get("JKS_AGENT_ENDPOINT", ""),
        agent_token=os.environ.get("JKS_AGENT_TOKEN", ""),
        stt_provider=os.environ.get("JKS_STT_PROVIDER", ""),
        stt_endpoint=os.environ.get("JKS_STT_ENDPOINT", ""),
        tts_provider=os.environ.get("JKS_TTS_PROVIDER", ""),
        tts_endpoint=os.environ.get("JKS_TTS_ENDPOINT", ""),
        tts_voice=os.environ.get("JKS_TTS_VOICE", "default"),
        oled_port=os.environ.get("JKS_OLED_PORT", "/dev/cu.usbmodem5B900048301"),
        oled_baud=_int_env("JKS_OLED_BAUD", 115200),
    )
