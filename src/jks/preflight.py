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

    def add_missing(name: str) -> None:
        if name not in missing:
            missing.append(name)

    if config.agent_endpoint:
        agent_mode = "http"
    else:
        agent_mode = "missing"
        add_missing("JKS_AGENT_ENDPOINT")

    has_stt = bool(config.stt_endpoint)
    has_tts = bool(config.tts_endpoint)
    wants_http_stt = config.stt_provider.lower() == "http" or has_stt
    wants_http_tts = config.tts_provider.lower() == "http" or has_tts
    wants_http_speech = wants_http_stt or wants_http_tts

    if has_stt and has_tts:
        speech_mode = "http"
    elif not wants_http_speech:
        speech_mode = "fake"
    else:
        speech_mode = "partial"
        if not has_stt:
            add_missing("JKS_STT_ENDPOINT")
        if not has_tts:
            add_missing("JKS_TTS_ENDPOINT")
        warnings.append("JKS_STT_ENDPOINT and JKS_TTS_ENDPOINT must be configured together")

    if agent_mode == "http" and speech_mode == "fake":
        add_missing("JKS_STT_ENDPOINT")
        add_missing("JKS_TTS_ENDPOINT")
        warnings.append("Real agent integration requires JKS_STT_ENDPOINT and JKS_TTS_ENDPOINT")

    oled_mode = "serial" if config.oled_port else "disabled"
    if not config.oled_port:
        add_missing("JKS_OLED_PORT")

    ready_for_real = agent_mode == "http" and speech_mode == "http" and oled_mode == "serial"
    ok = ready_for_real
    return {
        "ok": ok,
        "ready_for_real": ready_for_real,
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
