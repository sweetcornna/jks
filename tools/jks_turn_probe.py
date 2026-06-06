"""Run one configured STT -> Agent -> TTS turn from a provided WAV file."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
from typing import Optional, Sequence, TextIO
from uuid import uuid4

from jks.agent import HttpAgentClient
from jks.audio import AudioPlayer
from jks.config import load_config
from jks.preflight import analyze_config
from jks.speech import HttpSpeechClient


def _empty_summary() -> dict[str, object]:
    return {
        "ok": False,
        "preflight": {},
        "checks": {},
        "server_events": [],
        "errors": [],
    }


def _parse_args(argv: Sequence[str]) -> tuple[Optional[Path], bool, list[dict[str, str]]]:
    audio_path: Optional[Path] = None
    play = False
    errors: list[dict[str, str]] = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--audio":
            if index + 1 >= len(argv):
                errors.append({"error": "audio", "message": "--audio requires a path"})
                break
            audio_path = Path(argv[index + 1])
            index += 2
            continue
        if arg == "--play":
            play = True
            index += 1
            continue
        errors.append({"error": "args", "message": f"unsupported argument: {arg}"})
        index += 1

    if audio_path is None and not errors:
        errors.append({"error": "audio", "message": "--audio is required"})
    return audio_path, play, errors


def _dumps_compact_redacted_safe(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace(": ", "\\u003a ")


def run_turn_probe(argv: Sequence[str]) -> dict[str, object]:
    summary = _empty_summary()
    audio_path, play, errors = _parse_args(argv)
    if errors:
        summary["errors"] = errors
        return summary

    assert audio_path is not None
    if not audio_path.exists():
        summary["errors"] = [{"error": "audio", "message": f"audio file not found: {audio_path}"}]
        return summary

    config = load_config()
    preflight = analyze_config(config)
    summary["preflight"] = preflight
    if not preflight.get("ok"):
        return summary

    checks: dict[str, object] = {}
    server_events: list[str] = []
    errors = []
    try:
        output_dir = Path(tempfile.gettempdir()) / "jks-turn-probe"
        speech = HttpSpeechClient(config.stt_endpoint, config.tts_endpoint, output_dir)
        agent = HttpAgentClient(config.agent_endpoint, config.agent_token)

        user_text = speech.transcribe(audio_path)
        server_events.append("stt")
        checks["stt"] = {"text": user_text, "text_length": len(user_text)}

        reply = agent.send_message(user_text, f"turn-probe-{uuid4().hex}")
        server_events.append("chat")
        checks["agent"] = {
            "text": reply.text,
            "text_length": len(reply.text),
            "emotion": reply.emotion,
        }

        audio_reply = speech.synthesize(reply.text, config.tts_voice)
        server_events.append("tts")
        checks["tts"] = {
            "bytes": audio_reply.stat().st_size,
            "voice": config.tts_voice,
        }

        if play:
            AudioPlayer().play(audio_reply)
            checks["playback"] = {"played": True}
    except Exception as exc:
        errors.append({"error": "turn", "message": str(exc)})

    summary["checks"] = checks
    summary["server_events"] = server_events
    summary["errors"] = errors
    summary["ok"] = not errors and server_events == ["stt", "chat", "tts"]
    return summary


def main(argv: Optional[Sequence[str]] = None, stdout: TextIO = sys.stdout) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]
    try:
        summary = run_turn_probe(args)
    except Exception as exc:
        summary = _empty_summary()
        summary["errors"] = [{"error": "config", "message": str(exc)}]
    stdout.write(_dumps_compact_redacted_safe(summary) + "\n")
    return 0 if summary.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
