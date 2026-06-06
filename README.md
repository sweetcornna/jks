# JKS

Local voice-agent controller with an external OLED expression companion.

JKS lets a desktop app run a voice-call-like loop:

```text
voice button -> recording -> STT -> Hermes / Gran Agent -> TTS playback -> OLED expression
```

The remote agent handles conversation reasoning. The local controller owns microphone recording, audio playback, serial I/O, and OLED safety filtering.

## Hardware Baseline

- Board: ESP32-C3
- Firmware route: MicroPython
- Display: 128x64 I2C OLED
- Controller: SH1106
- I2C address: `0x3C`
- SDA: GPIO4
- SCL: GPIO5
- Baud: `115200`
- Observed serial port on this Mac: `/dev/cu.usbmodem5B900048301`

## Setup

```bash
uv sync
cp .env.example .env
```

Fill `.env` locally. Do not commit secrets.
The app and CLI tools load `.env` from the current working directory by default;
shell environment variables override file values. Placeholder values such as
`replace-with-*` intentionally fail readiness checks.

Required real-service values:

```text
JKS_AGENT_ENDPOINT
JKS_STT_PROVIDER
JKS_TTS_PROVIDER
JKS_TTS_VOICE
JKS_OLED_PORT
JKS_OLED_BAUD
```

`JKS_AGENT_TOKEN` is optional when the endpoint does not require bearer auth.

### Hermes API Server

For the local Hermes Agent API server, use its OpenAI-compatible Chat
Completions endpoint:

```dotenv
JKS_AGENT_ENDPOINT="http://127.0.0.1:8642/v1/chat/completions"
JKS_AGENT_TOKEN="replace-with-hermes-api-server-key"
```

`JKS_AGENT_TOKEN` must match the Hermes `API_SERVER_KEY` value. JKS sends
`model:"hermes-agent"`, a single user message, `stream:false`, and a
`X-Hermes-Session-Id` header for conversation continuity.

### Fish Audio Speech

For Fish Audio STT/TTS, set both speech providers to `fish` and keep the API
key only in local `.env`:

```dotenv
JKS_STT_PROVIDER="fish"
JKS_TTS_PROVIDER="fish"
JKS_FISH_API_KEY="replace-with-fish-api-key"
JKS_FISH_TTS_MODEL="s2-pro"
JKS_TTS_VOICE="default"
```

`JKS_TTS_VOICE` may be a Fish Audio `reference_id` / voice model id. When it is
`default`, JKS omits `reference_id`. Fish ASR uses `POST
https://api.fish.audio/v1/asr` with bearer auth and an `audio` form field. Fish
TTS uses `POST https://api.fish.audio/v1/tts`, `model:s2-pro`, and writes mp3
audio for playback.

For non-Fish HTTP speech adapters, configure `JKS_STT_ENDPOINT` and
`JKS_TTS_ENDPOINT`. `JKS_STT_TOKEN` and `JKS_TTS_TOKEN` are optional bearer
tokens for those custom endpoints.

Run the desktop controller:

```bash
uv run jks
```

## Verification

Run all tests:

```bash
uv run python -m unittest discover -s tests -v
```

Run the local fake STT / Agent / TTS smoke:

```bash
uv run python -m tools.jks_smoke
```

Check configuration readiness without printing secrets:

```bash
uv run python -m tools.jks_config_check
```

Probe configured real contracts:

```bash
uv run python -m tools.jks_contract_probe
```

Run a chained no-GUI/no-mic turn probe with a real audio file:

```bash
uv run python -m tools.jks_turn_probe --audio /path/to/input.wav
```

Run OLED hardware smoke:

```bash
uv run python -m tools.oled_smoke --port /dev/cu.usbmodem5B900048301
```

## Firmware

The working firmware files are:

- `firmware/micropython/main.py`
- `firmware/micropython/ssd1306_min.py`

Upload updated firmware with:

```bash
mpremote connect /dev/cu.usbmodem5B900048301 fs cp firmware/micropython/main.py :main.py
mpremote connect /dev/cu.usbmodem5B900048301 reset
```

If `mpremote` is not on `PATH` on this Mac, use the verified local binary:

```bash
/tmp/jks-pio/bin/mpremote connect /dev/cu.usbmodem5B900048301 fs cp firmware/micropython/main.py :main.py
/tmp/jks-pio/bin/mpremote connect /dev/cu.usbmodem5B900048301 reset
```

The OLED protocol is newline-delimited JSON. Example:

```json
{"cmd":"emotion","name":"happy","text":"DONE","duration_ms":1200,"intensity":"normal"}
```

Allowed emotions:

```text
neutral happy thinking speaking listening surprised sleepy sad angry error
```

## Documentation

See [PROJECT_PLAN.md](PROJECT_PLAN.md) for the Chinese project plan and phased roadmap.
Use [docs/MANUAL_ACCEPTANCE.md](docs/MANUAL_ACCEPTANCE.md) for the real-service and GUI/OLED acceptance checklist.
