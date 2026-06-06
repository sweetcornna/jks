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
- Visible desktop GUI evidence was captured outside the repository under `/tmp/jks-acceptance-evidence/gui-visible-01.png`, `/tmp/jks-acceptance-evidence/gui-visible-02.png`, and `/tmp/jks-acceptance-evidence/gui-visible-03.png`; `gui-visible-probe.json` reports `ok:true`, `shown:true`, two clicks, playback true, and no missing OLED ACKs.
- `uv run python -m tools.jks_visual_evidence --camera-device 1 --seconds 8 --hold-ms 500 --output-dir /tmp/jks-acceptance-evidence`: command returned `ok:true` and wrote `oled-camera.mp4`; visual review showed the camera was not aimed at the OLED, so this video is not acceptable physical OLED evidence.

## Remaining Manual Evidence

The terminal can verify serial ACKs, playback invocation, visible and hidden Tk
GUI state, and real service responses. The only remaining acceptance item is a
physical photo or short video where the external OLED is actually in frame and
readable across the required moods. Re-aim a camera at the OLED and rerun the
visual capture helper in `docs/MANUAL_ACCEPTANCE.md`, then visually review the
result before marking human-facing acceptance complete.
