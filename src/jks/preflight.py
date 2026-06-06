from __future__ import annotations

from urllib.parse import parse_qsl, quote_plus, urlsplit, urlunsplit

from .config import AppConfig


def redact_secret(value: str) -> str:
    if not value:
        return ""
    return f"<redacted:{len(value)}>"


def redact_url(value: str) -> str:
    if not value:
        return ""
    try:
        parts = urlsplit(value)
    except ValueError:
        return "<redacted-url>"
    if not parts.scheme or not parts.netloc:
        return value

    host = parts.hostname or ""
    try:
        port = parts.port
    except ValueError:
        return "<redacted-url>"
    if port is not None:
        host = f"{host}:{port}"
    query = "&".join(
        f"{quote_plus(key)}=<redacted>" for key, _ in parse_qsl(parts.query, keep_blank_values=True)
    )
    return urlunsplit((parts.scheme, host, parts.path, query, parts.fragment))


def analyze_config(config: AppConfig) -> dict[str, object]:
    missing: list[str] = []
    warnings: list[str] = []

    if config.agent_endpoint:
        agent_mode = "http"
    else:
        agent_mode = "missing"
        missing.append("JKS_AGENT_ENDPOINT")

    has_stt = bool(config.stt_endpoint)
    has_tts = bool(config.tts_endpoint)
    if has_stt and has_tts:
        speech_mode = "http"
    elif not has_stt and not has_tts:
        speech_mode = "fake"
    else:
        speech_mode = "partial"
        if not has_stt:
            missing.append("JKS_STT_ENDPOINT")
        if not has_tts:
            missing.append("JKS_TTS_ENDPOINT")
        warnings.append("JKS_STT_ENDPOINT and JKS_TTS_ENDPOINT must be configured together")

    oled_mode = "serial" if config.oled_port else "disabled"
    if not config.oled_port:
        missing.append("JKS_OLED_PORT")

    ok = agent_mode == "http" and speech_mode in {"http", "fake"} and oled_mode == "serial"
    return {
        "ok": ok,
        "agent": {
            "mode": agent_mode,
            "endpoint": redact_url(config.agent_endpoint),
            "host": config.agent_host,
            "user": config.agent_user,
            "auth_method": config.agent_auth_method,
            "token": redact_secret(config.agent_token),
        },
        "speech": {
            "mode": speech_mode,
            "stt_provider": config.stt_provider,
            "stt_endpoint": redact_url(config.stt_endpoint),
            "tts_provider": config.tts_provider,
            "tts_endpoint": redact_url(config.tts_endpoint),
            "voice": config.tts_voice,
        },
        "oled": {
            "mode": oled_mode,
            "port": config.oled_port,
            "baud": config.oled_baud,
        },
        "missing": missing,
        "warnings": warnings,
    }
