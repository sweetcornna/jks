from __future__ import annotations

from dataclasses import dataclass
import json
import os
import select
import termios
from typing import BinaryIO, Mapping, Optional


ALLOWED_EMOTIONS = {
    "neutral",
    "happy",
    "thinking",
    "speaking",
    "listening",
    "surprised",
    "sleepy",
    "sad",
    "angry",
    "error",
}

ALLOWED_EYE_STYLES = {
    "dot",
    "blink",
    "happy",
    "wide",
    "side",
    "sleepy",
    "sad",
    "angry",
    "cross",
}

ALLOWED_MOUTH_STYLES = {
    "flat",
    "smile",
    "small",
    "open",
    "talk1",
    "talk2",
    "sad",
}

ALLOWED_MOTIONS = {
    "still",
    "blink",
    "bob",
    "shake",
    "talk",
    "bounce",
}

def _build_baud_rates() -> dict[int, int]:
    rates = {}
    for baud in (9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600):
        name = f"B{baud}"
        if hasattr(termios, name):
            rates[baud] = getattr(termios, name)
    return rates


_BAUD_RATES = _build_baud_rates()


@dataclass(frozen=True)
class FacePattern:
    left_eye: str = "dot"
    right_eye: str = "dot"
    mouth: str = "flat"
    x_offset: int = 0
    y_offset: int = 0
    motion: str = "bob"


@dataclass(frozen=True)
class DisplayIntent:
    emotion: str
    text: str = ""
    duration_ms: int = 1200
    intensity: str = "normal"
    pattern: Optional[FacePattern] = None


def _oled_text(text: object, limit: int = 14) -> str:
    printable = "".join(ch for ch in str(text) if " " <= ch <= "~")
    return printable[:limit]


class DisplayController:
    def __init__(self, output: BinaryIO, ack_input: Optional[BinaryIO] = None):
        self._output = output
        self._ack_input = ack_input

    def show(self, intent: DisplayIntent) -> None:
        emotion = intent.emotion if intent.emotion in ALLOWED_EMOTIONS else "neutral"
        text = intent.text or emotion.upper()
        payload = {
            "cmd": "emotion",
            "name": emotion,
            "text": _oled_text(text),
            "duration_ms": _duration_ms(intent.duration_ms),
            "intensity": _intensity(intent.intensity),
        }
        if intent.pattern is not None:
            pattern = _face_pattern(intent.pattern)
            payload.update(
                {
                    "cmd": "face",
                    "left_eye": pattern.left_eye,
                    "right_eye": pattern.right_eye,
                    "mouth": pattern.mouth,
                    "x_offset": pattern.x_offset,
                    "y_offset": pattern.y_offset,
                    "motion": pattern.motion,
                }
            )
        self._write(payload)

    def clear(self) -> None:
        self._write({"cmd": "clear"})

    def probe(self) -> None:
        self._write({"cmd": "probe"})

    def read_ack(self, timeout: float = 0.0) -> Optional[dict[str, object]]:
        if self._ack_input is None:
            return None
        try:
            ready, _, _ = select.select([self._ack_input], [], [], timeout)
        except (OSError, TypeError, ValueError):
            ready = [self._ack_input]
        if not ready:
            return None

        line = self._ack_input.readline()
        if not line:
            return None
        if isinstance(line, bytes):
            line = line.decode("utf-8")
        return json.loads(line)

    def _write(self, payload: Mapping[str, object]) -> None:
        frame = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        self._output.write(frame.encode("utf-8") + b"\n")
        self._output.flush()


class NullDisplayController:
    def show(self, intent: DisplayIntent) -> None:
        return None

    def clear(self) -> None:
        return None

    def probe(self) -> None:
        return None

    def read_ack(self, timeout: float = 0.0) -> None:
        return None


def _baud_constant(baud: int) -> int:
    if baud not in _BAUD_RATES:
        supported = ", ".join(str(rate) for rate in sorted(_BAUD_RATES))
        raise ValueError(f"unsupported baud rate {baud}; choose one of: {supported}")
    return _BAUD_RATES[baud]


def _duration_ms(raw: object) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 1200
    return max(200, min(value, 5000))


def _intensity(raw: object) -> str:
    value = str(raw)
    if value in {"soft", "normal", "high"}:
        return value
    return "normal"


def _face_pattern(pattern: FacePattern) -> FacePattern:
    return FacePattern(
        left_eye=_eye_style(pattern.left_eye),
        right_eye=_eye_style(pattern.right_eye),
        mouth=_mouth_style(pattern.mouth),
        x_offset=_offset(pattern.x_offset),
        y_offset=_offset(pattern.y_offset),
        motion=_motion(pattern.motion),
    )


def _eye_style(raw: object) -> str:
    value = str(raw)
    if value in ALLOWED_EYE_STYLES:
        return value
    return "dot"


def _mouth_style(raw: object) -> str:
    value = str(raw)
    if value in ALLOWED_MOUTH_STYLES:
        return value
    return "flat"


def _offset(raw: object) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    return max(-4, min(value, 4))


def _motion(raw: object) -> str:
    value = str(raw)
    if value in ALLOWED_MOTIONS:
        return value
    return "bob"


def _configure_serial_fd(fd: int, baud: int) -> None:
    baud_constant = _baud_constant(baud)
    attrs = termios.tcgetattr(fd)
    attrs[0] &= ~(
        termios.IGNBRK
        | termios.BRKINT
        | termios.PARMRK
        | termios.ISTRIP
        | termios.INLCR
        | termios.IGNCR
        | termios.ICRNL
        | termios.IXON
        | termios.IXOFF
        | termios.IXANY
    )
    attrs[1] &= ~termios.OPOST
    attrs[2] &= ~(termios.CSIZE | termios.PARENB)
    attrs[2] |= termios.CS8 | termios.CLOCAL | termios.CREAD
    attrs[3] &= ~(termios.ECHO | termios.ECHONL | termios.ICANON | termios.ISIG | termios.IEXTEN)
    attrs[4] = baud_constant
    attrs[5] = baud_constant
    termios.tcsetattr(fd, termios.TCSANOW, attrs)


def open_serial_output(path: str, baud: int) -> BinaryIO:
    _baud_constant(baud)
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY)
    try:
        if os.isatty(fd):
            _configure_serial_fd(fd, baud)
        return os.fdopen(fd, "r+b", buffering=0)
    except Exception:
        os.close(fd)
        raise
