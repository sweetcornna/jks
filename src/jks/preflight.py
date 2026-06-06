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


def _is_placeholder(value: str) -> bool:
    return value.strip().lower().startswith("replace-with-")


def _is_http_url(value: str) -> bool:
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    return parts.scheme in {"http", "https"} and bool(parts.netloc)


def analyze_config(config: AppConfig) -> dict[str, object]:
    missing: list[str] = []
    warnings: list[str] = []

    def add_missing(name: str) -> None:
        if name not in missing:
            missing.append(name)

    def add_warning(message: str) -> None:
        if message not in warnings:
            warnings.append(message)

    def field_has_placeholder(value: str, name: str) -> bool:
        if value and _is_placeholder(value):
            add_missing(name)
            add_warning("placeholder values must be replaced before real integration")
            return True
        return False

    def endpoint_is_ready(value: str, name: str) -> bool:
        if not value:
            return False
        if field_has_placeholder(value, name):
            return False
        if not _is_http_url(value):
            add_missing(name)
            add_warning("endpoint values must be valid http(s) URLs")
            return False
        return True

    agent_token_placeholder = field_has_placeholder(config.agent_token, "JKS_AGENT_TOKEN")
    tts_voice_placeholder = field_has_placeholder(config.tts_voice, "JKS_TTS_VOICE")

    agent_endpoint_ready = endpoint_is_ready(config.agent_endpoint, "JKS_AGENT_ENDPOINT")
    if agent_endpoint_ready:
        agent_mode = "http"
    else:
        agent_mode = "missing"
        if not config.agent_endpoint:
            add_missing("JKS_AGENT_ENDPOINT")

    stt_endpoint_ready = endpoint_is_ready(config.stt_endpoint, "JKS_STT_ENDPOINT")
    tts_endpoint_ready = endpoint_is_ready(config.tts_endpoint, "JKS_TTS_ENDPOINT")
    wants_http_stt = config.stt_provider.lower() == "http" or bool(config.stt_endpoint)
    wants_http_tts = config.tts_provider.lower() == "http" or bool(config.tts_endpoint)
    wants_http_speech = wants_http_stt or wants_http_tts

    if stt_endpoint_ready and tts_endpoint_ready:
        speech_mode = "http"
    elif not wants_http_speech:
        speech_mode = "fake"
    else:
        speech_mode = "partial"
        if not stt_endpoint_ready:
            add_missing("JKS_STT_ENDPOINT")
        if not tts_endpoint_ready:
            add_missing("JKS_TTS_ENDPOINT")
        add_warning("JKS_STT_ENDPOINT and JKS_TTS_ENDPOINT must be configured together")

    if agent_mode == "http" and speech_mode == "fake":
        add_missing("JKS_STT_ENDPOINT")
        add_missing("JKS_TTS_ENDPOINT")
        add_warning("Real agent integration requires JKS_STT_ENDPOINT and JKS_TTS_ENDPOINT")

    oled_port_placeholder = field_has_placeholder(config.oled_port, "JKS_OLED_PORT")
    oled_mode = "serial" if config.oled_port and not oled_port_placeholder else "disabled"
    if not config.oled_port:
        add_missing("JKS_OLED_PORT")

    ready_for_real = (
        agent_mode == "http"
        and speech_mode == "http"
        and oled_mode == "serial"
        and not agent_token_placeholder
        and not tts_voice_placeholder
    )
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
