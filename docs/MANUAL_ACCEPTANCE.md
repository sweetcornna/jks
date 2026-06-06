# JKS Manual Acceptance Checklist

Use this checklist only after `.env` contains a real local Hermes / Gran Agent
endpoint plus either Fish Audio speech credentials or custom STT/TTS endpoints.

For Hermes API Server, set:

```dotenv
JKS_AGENT_ENDPOINT="http://127.0.0.1:8642/v1/chat/completions"
JKS_AGENT_TOKEN="replace-with-local-api-server-key"
JKS_AGENT_MODEL="hermes-agent"
```

The token must match Hermes `API_SERVER_KEY`.
If the Hermes profile exposes a different model name, set `JKS_AGENT_MODEL` to
that value.

If the VPS only exposes the Hermes CLI over SSH, set:

```dotenv
JKS_AGENT_HOST="replace-with-agent-host"
JKS_AGENT_USER="replace-with-agent-user"
JKS_AGENT_AUTH_METHOD="ssh-password"
JKS_AGENT_SSH_PASSWORD="replace-with-local-ssh-password"
JKS_AGENT_COMMAND="/usr/local/lib/hermes-agent/venv/bin/hermes"
JKS_AGENT_WORKDIR="/usr/local/lib/hermes-agent"
```

For Fish Audio speech, set:

```dotenv
JKS_STT_PROVIDER="fish"
JKS_TTS_PROVIDER="fish"
JKS_FISH_API_KEY="replace-with-fish-api-key"
JKS_FISH_TTS_MODEL="s2-pro"
JKS_TTS_VOICE="default"
```

Use a Fish voice/reference id in `JKS_TTS_VOICE` if a specific voice is needed.
`FISH_AUDIO_API_KEY` and `FISH_API_KEY` are accepted aliases for existing Fish
Audio configs.

## Preflight

```bash
uv run python -m tools.jks_smoke
uv run python -m tools.jks_agent_probe
uv run python -m tools.jks_config_check
uv run python -m tools.jks_mic_probe --duration 1 --min-rms 0.0001
uv run python -m tools.jks_contract_probe
uv run python -m tools.jks_turn_probe --audio /path/to/input.wav --display --require-display-ack --display-ack-timeout 6 --play
uv run python -m tools.jks_app_probe --audio /path/to/input.wav --require-display-ack --display-ack-timeout 6 --play
uv run python -m tools.jks_gui_probe --audio /path/to/input.wav --require-display-ack --display-ack-timeout 6 --play
uv run python -m tools.oled_smoke
```

Expected:

- `jks_smoke`: `ok:true`
- `jks_agent_probe`: `ok:true`
- `jks_config_check`: `ok:true`
- `jks_mic_probe`: `ok:true`, non-zero `rms` / `peak`
- `jks_contract_probe`: `ok:true`
- `jks_turn_probe`: `server_events:["stt","chat","tts"]`
- `jks_turn_probe`: `display_events` includes listening/transcribing/thinking/speaking/agent and no missing ACKs
- `jks_app_probe`: `ui.clicks:2`, `orchestrator.run_voice_turn_calls:0`, `server_events:["stt","chat","tts"]`, `playback.played:true`
- `jks_gui_probe`: `gui.clicks:2`, `gui.status:"Ready"`, `server_events:["stt","chat","tts"]`, `playback.played:true`
- `oled_smoke`: `ok:true`

`jks_turn_probe` prints text lengths by default, not full transcripts. Add
`--verbose` only when local transcript logging is acceptable.
`oled_smoke` reads `JKS_OLED_PORT` and `JKS_OLED_BAUD`; add `--hold-ms 2000`
when capturing visual evidence.

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
- If the agent returns JSON content with `text`, `emotion`, and optional `display_text`, the spoken text and OLED expression both reflect it.
- On OLED disconnect, the desktop still completes the voice turn and shows an OLED degraded prompt.
- On STT / Agent / TTS failure, the UI preserves the available audio path, user text, or agent text.

## Visual Evidence

Capture at least one photo or short video showing:

- `neutral`
- `listening`
- `thinking`
- `speaking`
- `happy`
- `surprised`
- `sleepy`
- `sad`
- `angry`
- `error`

Visual pass criteria:

- Short OLED labels are readable and not cropped.
- Eye and mouth changes are visible between moods.
- Animation cadence feels alive rather than static or flickery.
- `speaking` is visible while audio playback is active.
- The display returns to a completion or agent-selected expression after playback.

Save visual evidence outside the repository unless it is intentionally redacted and safe to publish.
