# JKS Manual Acceptance Checklist

Use this checklist only after `.env` contains real local endpoints or proxies for Hermes / Gran, STT, and TTS.

For Hermes API Server, set:

```dotenv
JKS_AGENT_ENDPOINT="http://127.0.0.1:8642/v1/chat/completions"
JKS_AGENT_TOKEN="replace-with-local-api-server-key"
```

The token must match Hermes `API_SERVER_KEY`.

For Fish Audio speech, set:

```dotenv
JKS_STT_PROVIDER="fish"
JKS_TTS_PROVIDER="fish"
JKS_FISH_API_KEY="replace-with-fish-api-key"
JKS_FISH_TTS_MODEL="s2-pro"
JKS_TTS_VOICE="default"
```

Use a Fish voice/reference id in `JKS_TTS_VOICE` if a specific voice is needed.

## Preflight

```bash
uv run python -m tools.jks_config_check
uv run python -m tools.jks_contract_probe
uv run python -m tools.jks_turn_probe --audio /path/to/input.wav --play
uv run python -m tools.oled_smoke --port /dev/cu.usbmodem5B900048301
```

Expected:

- `jks_config_check`: `ok:true`
- `jks_contract_probe`: `ok:true`
- `jks_turn_probe`: `server_events:["stt","chat","tts"]`
- `oled_smoke`: `ok:true`

## Desktop Turn

```bash
uv run jks
```

Record:

- First click changes status to `Listening`.
- OLED shows listening animation.
- Second click changes status through `Transcribing`, `Thinking`, and `Speaking`.
- Transcript shows `You:` and `Agent:` text.
- Agent reply is played as audio.
- OLED shows speaking during playback and a completion or agent-selected expression after playback.
- On OLED disconnect, the desktop still completes the voice turn and shows an OLED degraded prompt.
- On STT / Agent / TTS failure, the UI preserves the available audio path, user text, or agent text.

## Visual Evidence

Capture at least one photo or short video showing:

- `listening`
- `thinking`
- `speaking`
- `happy`
- `error`

Save visual evidence outside the repository unless it is intentionally redacted and safe to publish.
