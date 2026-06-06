# JKS Acceptance Results

Date: 2026-06-06

This record intentionally omits endpoint, host, username, password, token,
runtime path, OLED port, transcript text, and API key values. Real-service
probes were run with secrets supplied through the shell environment only.

## Automated Gates

- `uv run python -m tools.jks_agent_probe`: `ok:true`; SSH Hermes mode; agent reply text present; display intent present.
- `uv run python -m tools.jks_config_check`: `ok:true`; `ready_for_real:true`; SSH Hermes + Fish speech + serial OLED.
- `uv run python -m tools.jks_mic_probe --duration 1 --min-rms 0.0001 --timeout 3`: `ok:true`; non-zero RMS and peak.
- `uv run python -m tools.jks_contract_probe`: `ok:true`; Hermes Agent and Fish speech contract checks passed.
- `uv run python -m tools.jks_turn_probe --audio /tmp/jks-real-turn.mp3 --display --require-display-ack --display-ack-timeout 6 --play`: `ok:true`; `server_events:["stt","chat","tts"]`; playback true; OLED ACKs present for listening, thinking, thinking, speaking, and agent expression.
- `uv run python -m tools.jks_app_probe --audio /tmp/jks-real-turn.mp3 --require-display-ack --display-ack-timeout 6 --play`: `ok:true`; two UI clicks; start/finish orchestrator path; playback true; no missing OLED ACKs.
- `uv run python -m tools.jks_gui_probe --audio /tmp/jks-real-turn.mp3 --require-display-ack --display-ack-timeout 6 --play`: `ok:true`; real Tk app created; two Speak button clicks; final status Ready; playback true; no missing OLED ACKs.
- `uv run python -m tools.oled_smoke --hold-ms 1000`: `ok:true`; ACKs received for probe, all base emotions, text, and clear.

## Remaining Manual Evidence

The terminal can verify serial ACKs, playback invocation, hidden Tk GUI state,
and real service responses. It cannot independently capture a physical photo or
short video of the external OLED. For final human-facing acceptance, capture
the visual evidence listed in `docs/MANUAL_ACCEPTANCE.md` outside the repository.
