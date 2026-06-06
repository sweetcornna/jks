from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Optional

from .display import ALLOWED_EMOTIONS, DisplayIntent


class TurnState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ERROR = "error"


STATE_INTENTS = {
    TurnState.IDLE: DisplayIntent("neutral", "READY"),
    TurnState.LISTENING: DisplayIntent("listening", "HEAR"),
    TurnState.TRANSCRIBING: DisplayIntent("thinking", "TEXT"),
    TurnState.THINKING: DisplayIntent("thinking", "WAIT"),
    TurnState.SPEAKING: DisplayIntent("speaking", "TALK"),
    TurnState.ERROR: DisplayIntent("error", "OOPS"),
}


@dataclass(frozen=True)
class ExpressionFrame:
    emotion: str
    text: str
    duration_ms: int


def _clamp_oled_text(text: object, limit: int = 14) -> str:
    printable = "".join(ch for ch in str(text) if " " <= ch <= "~")
    return printable[:limit]


class ExpressionEngine:
    def intent_for_state(self, state: TurnState) -> DisplayIntent:
        return STATE_INTENTS[state]

    def intent_from_agent(self, payload: Optional[Mapping[str, object]]) -> DisplayIntent:
        if payload is None:
            payload = {}
        raw_emotion = str(payload.get("emotion", "neutral"))
        emotion = raw_emotion if raw_emotion in ALLOWED_EMOTIONS else "neutral"
        raw_text = payload.get("display_text")
        if raw_text is None:
            raw_text = emotion.upper()
        text = _clamp_oled_text(raw_text)
        duration_ms = self._clamp_duration(payload.get("duration_ms", 1200))
        intensity = str(payload.get("intensity", "normal"))
        if intensity not in {"soft", "normal", "high"}:
            intensity = "normal"
        return DisplayIntent(
            emotion=emotion,
            text=text,
            duration_ms=duration_ms,
            intensity=intensity,
        )

    def frames_for(self, emotion: str) -> list[ExpressionFrame]:
        if emotion == "speaking":
            return [
                ExpressionFrame("speaking", "TALK", 160),
                ExpressionFrame("speaking", "talk", 160),
                ExpressionFrame("speaking", "TALK!", 220),
            ]
        if emotion == "thinking":
            return [
                ExpressionFrame("thinking", "WAIT", 240),
                ExpressionFrame("thinking", "hmm?", 240),
                ExpressionFrame("thinking", "...", 280),
            ]
        if emotion == "happy":
            return [
                ExpressionFrame("happy", "YAY", 180),
                ExpressionFrame("happy", "^_^", 220),
                ExpressionFrame("happy", "DONE", 260),
            ]
        if emotion == "listening":
            return [
                ExpressionFrame("listening", "HEAR", 200),
                ExpressionFrame("listening", "o_o", 220),
                ExpressionFrame("listening", "...", 260),
            ]
        if emotion == "surprised":
            return [
                ExpressionFrame("surprised", "WOW", 180),
                ExpressionFrame("surprised", "O_O", 240),
                ExpressionFrame("surprised", "!!", 220),
            ]
        if emotion == "sleepy":
            return [
                ExpressionFrame("sleepy", "zzz", 420),
                ExpressionFrame("sleepy", "-_-", 420),
                ExpressionFrame("sleepy", "Zzz", 520),
            ]
        if emotion == "sad":
            return [
                ExpressionFrame("sad", "oh", 260),
                ExpressionFrame("sad", "T_T", 360),
                ExpressionFrame("sad", "...", 420),
            ]
        if emotion == "angry":
            return [
                ExpressionFrame("angry", "HEY", 180),
                ExpressionFrame("angry", ">_<", 180),
                ExpressionFrame("angry", "!!", 220),
            ]
        if emotion == "neutral":
            return [
                ExpressionFrame("neutral", "READY", 420),
                ExpressionFrame("neutral", "-_-", 120),
                ExpressionFrame("neutral", "READY", 520),
            ]
        if emotion == "error":
            return [
                ExpressionFrame("error", "OOPS", 180),
                ExpressionFrame("error", "! !", 180),
                ExpressionFrame("neutral", "READY", 600),
            ]
        return self.frames_for("neutral")

    def _clamp_duration(self, raw: object) -> int:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return 1200
        return max(200, min(value, 5000))
