from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, Sequence, TextIO

from .agent import AgentTraceEvent, build_agent_client
from .audio import AudioPlayer, AudioRecorder
from .config import AppConfig, load_config
from .display import (
    DisplayController,
    DisplayIntent,
    FacePattern,
    NullDisplayController,
    open_serial_output,
)
from .expression import ExpressionEngine, TurnState
from .orchestrator import ConversationOrchestrator
from .speech import build_speech_client


def build_orchestrator(
    config: AppConfig,
    *,
    open_serial: Callable[[str, int], object] = open_serial_output,
    output_dir: Optional[Path] = None,
    recorder=None,
    player=None,
    status_callback: Optional[Callable[[TurnState], None]] = None,
    display_status_callback: Optional[Callable[[str], None]] = None,
    display_error_callback: Optional[Callable[[str], None]] = None,
    agent_trace_callback: Optional[Callable[[AgentTraceEvent], None]] = None,
    display_update_callback: Optional[Callable[[object], None]] = None,
) -> ConversationOrchestrator:
    output_dir = Path(output_dir) if output_dir is not None else Path(tempfile.gettempdir())

    try:
        serial_output = open_serial(config.oled_port, config.oled_baud)
        display = DisplayController(serial_output, ack_input=serial_output)
    except Exception:
        if display_status_callback is not None:
            display_status_callback(
                f"OLED unavailable on {config.oled_port}; reconnect display and restart if needed."
            )
        display = NullDisplayController()

    speech = build_speech_client(config, output_dir)

    return ConversationOrchestrator(
        recorder=recorder or AudioRecorder(),
        speech=speech,
        agent=build_agent_client(config),
        display=display,
        player=player or AudioPlayer(),
        voice=config.tts_voice,
        status_callback=status_callback,
        display_error_callback=display_error_callback,
        agent_trace_callback=agent_trace_callback,
        display_update_callback=display_update_callback,
    )


STATE_LABELS = {
    TurnState.IDLE: "Ready",
    TurnState.LISTENING: "Listening",
    TurnState.TRANSCRIBING: "Transcribing",
    TurnState.THINKING: "Thinking",
    TurnState.SPEAKING: "Speaking",
    TurnState.ERROR: "Error",
}

DEFAULT_WINDOW_GEOMETRY = "560x420"
MIN_WINDOW_SIZE = (420, 320)
DISPLAY_ANIMATION_MS = 180


class JksApp:
    def __init__(self, root: tk.Tk, orchestrator: Optional[ConversationOrchestrator] = None):
        self.root = root
        self.root.title("JKS Voice Agent")
        self.root.geometry(DEFAULT_WINDOW_GEOMETRY)
        self.root.minsize(*MIN_WINDOW_SIZE)
        self.status = tk.StringVar(value="Ready")
        self.device_status = tk.StringVar(value="OLED ready")
        self.transcript = tk.StringVar(value="")
        self.agent_trace = tk.StringVar(value="Agent trace will appear here.")
        self.display_preview = tk.StringVar(value="neutral READY")
        self._trace_lines: list[str] = []
        self._display_animation_after = None
        self._display_animation_frame = 0
        self._display_animation_intent: Optional[DisplayIntent] = None
        self._display_animation_label = ""
        self._expression = ExpressionEngine()
        self.orchestrator = orchestrator or build_orchestrator(
            load_config(),
            status_callback=self._show_turn_state,
            display_status_callback=self._show_display_status,
            display_error_callback=self._show_display_status,
            agent_trace_callback=self._show_agent_trace,
        )
        if hasattr(self.orchestrator, "display_update_callback"):
            self.orchestrator.display_update_callback = self._show_display_preview
        self._recording = False

        self.button = ttk.Button(root, text="Speak", command=self.start_turn)
        self.button.pack(padx=16, pady=12)
        ttk.Label(root, textvariable=self.status).pack(padx=16, pady=4)
        ttk.Label(root, textvariable=self.device_status, wraplength=420).pack(padx=16, pady=4)
        self.display_canvas = _make_display_canvas(root)
        self.display_canvas.pack(padx=16, pady=(8, 2))
        ttk.Label(root, textvariable=self.display_preview, wraplength=420).pack(padx=16, pady=2)
        ttk.Label(root, textvariable=self.transcript, wraplength=420).pack(padx=16, pady=12)
        ttk.Label(root, text="Agent Trace").pack(padx=16, pady=(8, 2))
        ttk.Label(root, textvariable=self.agent_trace, wraplength=520).pack(padx=16, pady=4)
        self._render_display_preview(self._expression.intent_for_state(TurnState.IDLE))

    def start_turn(self) -> None:
        if not self._recording:
            self._start_recording()
            return

        self._stop_and_run_turn()

    def _start_recording(self) -> None:
        self.button.configure(state="disabled")
        self.status.set("Listening")
        self._reset_agent_trace()
        try:
            self.orchestrator.start_recording()
        except Exception as exc:
            self._finish_error(exc)
            return

        self._recording = True
        self.button.configure(text="Stop", state="normal")

    def _stop_and_run_turn(self) -> None:
        self._recording = False
        self.button.configure(state="disabled")
        self.status.set("Transcribing")
        thread = threading.Thread(target=self._run_turn, daemon=True)
        thread.start()

    def _run_turn(self) -> None:
        try:
            result = self.orchestrator.finish_voice_turn()
        except Exception as exc:
            self.root.after(0, lambda exc=exc: self._finish_error(exc))
            return
        self.root.after(0, lambda: self._finish_success(result))

    def _finish_success(self, result) -> None:
        self._recording = False
        if result.audio_error:
            self.status.set(f"Voice output failed: {result.audio_error}")
        else:
            self.status.set("Ready")
        self.transcript.set(f"You: {result.user_text}\nAgent: {result.agent_text}")
        if result.emotion:
            self._render_display_preview(
                DisplayIntent(
                    result.emotion,
                    getattr(result, "display_text", "") or result.emotion.upper(),
                    getattr(result, "display_duration_ms", 0) or 1200,
                    getattr(result, "display_intensity", "") or "normal",
                )
            )
        self.button.configure(text="Speak", state="normal")

    def _finish_error(self, exc: Exception) -> None:
        self._recording = False
        self.status.set(f"Error: {exc}")
        partial_lines = []
        user_text = getattr(exc, "user_text", "")
        audio_path = getattr(exc, "audio_path", None)
        if user_text:
            partial_lines.append(f"You: {user_text}")
        if audio_path:
            partial_lines.append(f"Audio: {audio_path}")
        if partial_lines:
            self.transcript.set("\n".join(partial_lines))
        self.button.configure(text="Speak", state="normal")

    def _show_turn_state(self, state: TurnState) -> None:
        label = STATE_LABELS.get(state, str(state))
        intent = self._expression.intent_for_state(state)
        self.root.after(0, lambda label=label, intent=intent: self._set_turn_state_ui(label, intent))

    def _show_display_status(self, message: str) -> None:
        self.root.after(0, lambda message=message: self.device_status.set(message))

    def _show_display_preview(self, intent: object) -> None:
        self.root.after(0, lambda intent=intent: self._render_display_preview(intent))

    def _show_agent_trace(self, event: AgentTraceEvent) -> None:
        self.root.after(0, lambda event=event: self._append_agent_trace(event))

    def _set_turn_state_ui(self, label: str, intent: DisplayIntent) -> None:
        self.status.set(label)
        self._render_display_preview(intent)

    def _render_display_preview(self, intent: object) -> None:
        if not isinstance(intent, DisplayIntent):
            self._cancel_display_animation()
            self._display_animation_intent = None
            self.display_preview.set("screen clear")
            _clear_display_canvas(self.display_canvas)
            return
        label = _preview_text(intent.text or intent.emotion.upper(), 16)
        self.display_preview.set(f"{intent.emotion} {label}")
        self._cancel_display_animation()
        self._display_animation_intent = intent
        self._display_animation_label = label
        self._display_animation_frame = 0
        _draw_display_canvas(self.display_canvas, intent.emotion, label, intent.pattern, frame=0)
        self._schedule_display_animation()

    def _schedule_display_animation(self) -> None:
        if self._display_animation_intent is None:
            return
        if not _supports_display_animation(self.root):
            return
        self._display_animation_after = self.root.after(
            DISPLAY_ANIMATION_MS,
            self._advance_display_animation,
        )

    def _advance_display_animation(self) -> None:
        intent = self._display_animation_intent
        if intent is None:
            return
        self._display_animation_frame += 1
        _draw_display_canvas(
            self.display_canvas,
            intent.emotion,
            self._display_animation_label,
            intent.pattern,
            frame=self._display_animation_frame,
        )
        self._schedule_display_animation()

    def _cancel_display_animation(self) -> None:
        if self._display_animation_after is None:
            return
        if hasattr(self.root, "after_cancel"):
            try:
                self.root.after_cancel(self._display_animation_after)
            except Exception:
                pass
        self._display_animation_after = None

    def _append_agent_trace(self, event: AgentTraceEvent) -> None:
        source = str(getattr(event, "source", "") or "agent").strip()
        message = str(getattr(event, "message", event)).strip()
        if not message:
            return
        line = f"{source}: {message}" if source else message
        if len(line) > 180:
            line = line[:179].rstrip() + "..."
        self._trace_lines.append(line)
        self._trace_lines = self._trace_lines[-10:]
        self.agent_trace.set("\n".join(self._trace_lines))

    def _reset_agent_trace(self) -> None:
        self._trace_lines = []
        self.agent_trace.set("Recording...")


class _NullDisplayCanvas:
    def pack(self, **kwargs) -> None:
        return None

    def delete(self, *args) -> None:
        return None

    def create_rectangle(self, *args, **kwargs) -> None:
        return None

    def create_oval(self, *args, **kwargs) -> None:
        return None

    def create_arc(self, *args, **kwargs) -> None:
        return None

    def create_line(self, *args, **kwargs) -> None:
        return None

    def create_text(self, *args, **kwargs) -> None:
        return None


def _make_display_canvas(root) -> object:
    try:
        return tk.Canvas(root, width=192, height=96, bg="#050505", highlightthickness=1)
    except Exception:
        return _NullDisplayCanvas()


def _clear_display_canvas(canvas) -> None:
    canvas.delete("all")
    canvas.create_rectangle(0, 0, 192, 96, fill="#050505", outline="#333333")


def _supports_display_animation(root) -> bool:
    return hasattr(root, "after") and hasattr(root, "after_cancel")


def _draw_display_canvas(
    canvas,
    emotion: str,
    label: str,
    pattern: Optional[FacePattern] = None,
    frame: int = 0,
) -> None:
    _clear_display_canvas(canvas)
    face = "#d8ff74"
    accent = "#72d7ff"
    canvas.create_rectangle(8, 8, 184, 88, outline="#5dff9a")
    if pattern is not None:
        motion_dx, motion_dy = _preview_motion_delta(pattern.motion, frame)
        dx = pattern.x_offset * 2 + motion_dx
        dy = pattern.y_offset * 2 + motion_dy
        left_eye = _preview_eye_for_motion(pattern.left_eye, pattern.motion, frame)
        right_eye = _preview_eye_for_motion(pattern.right_eye, pattern.motion, frame)
        mouth = _preview_mouth_for_motion(pattern.mouth, pattern.motion, frame)
        _draw_preview_eye(canvas, 54 + dx, 38 + dy, left_eye, face)
        _draw_preview_eye(canvas, 120 + dx, 38 + dy, right_eye, face)
        _draw_preview_mouth(canvas, mouth, face, dy)
    elif emotion in {"happy", "speaking"}:
        dx, dy = _preview_motion_delta("talk" if emotion == "speaking" else "bounce", frame)
        canvas.create_arc(50 + dx, 34 + dy, 78 + dx, 58 + dy, start=180, extent=180, outline=face, width=2)
        canvas.create_arc(114 + dx, 34 + dy, 142 + dx, 58 + dy, start=180, extent=180, outline=face, width=2)
        _draw_preview_mouth(canvas, "talk1" if emotion == "speaking" and frame % 2 else "smile", face, dy)
    elif emotion == "surprised":
        dx, dy = _preview_motion_delta("bob", frame)
        canvas.create_oval(52 + dx, 34 + dy, 76 + dx, 58 + dy, outline=face, width=2)
        canvas.create_oval(116 + dx, 34 + dy, 140 + dx, 58 + dy, outline=face, width=2)
        canvas.create_oval(86 + dx, 56 + dy, 106 + dx, 76 + dy, outline=face, width=2)
    elif emotion == "sleepy":
        _dx, dy = _preview_motion_delta("bob", frame)
        canvas.create_line(52, 48 + dy, 76, 48 + dy, fill=face, width=2)
        canvas.create_line(116, 48 + dy, 140, 48 + dy, fill=face, width=2)
        canvas.create_line(82, 66 + dy, 110, 66 + dy, fill=face, width=2)
    elif emotion in {"angry", "error"}:
        dx, dy = _preview_motion_delta("shake", frame)
        canvas.create_line(50 + dx, 38 + dy, 78 + dx, 52 + dy, fill=face, width=2)
        canvas.create_line(114 + dx, 52 + dy, 142 + dx, 38 + dy, fill=face, width=2)
        canvas.create_line(80 + dx, 66 + dy, 112 + dx, 62 + dy, fill=face, width=2)
    else:
        dx, dy = _preview_motion_delta("blink", frame)
        eye_style = "blink" if frame % 10 == 5 else "dot"
        _draw_preview_eye(canvas, 54 + dx, 38 + dy, eye_style, face)
        _draw_preview_eye(canvas, 120 + dx, 38 + dy, eye_style, face)
        canvas.create_line(82 + dx, 66 + dy, 110 + dx, 66 + dy, fill=face, width=2)
    if emotion in {"thinking", "listening"}:
        dots = "." * ((frame % 3) + 1)
        canvas.create_text(154, 28, text=dots, fill=accent, font=("Menlo", 13, "bold"))
    canvas.create_text(96, 82, text=label, fill="#f6f6f6", font=("Menlo", 12, "bold"))


def _draw_preview_eye(canvas, x: int, y: int, style: str, face: str) -> None:
    if style == "blink":
        canvas.create_line(x, y + 8, x + 20, y + 8, fill=face, width=2)
    elif style == "happy":
        canvas.create_arc(x - 2, y - 2, x + 22, y + 20, start=180, extent=180, outline=face, width=2)
    elif style == "wide":
        canvas.create_oval(x - 2, y - 4, x + 22, y + 20, outline=face, width=2)
        canvas.create_oval(x + 7, y + 4, x + 13, y + 10, fill=face, outline=face)
    elif style == "side":
        canvas.create_oval(x - 2, y, x + 22, y + 16, outline=face, width=2)
        canvas.create_oval(x + 3, y + 5, x + 9, y + 11, fill=face, outline=face)
    elif style == "sleepy":
        canvas.create_line(x, y + 6, x + 18, y + 6, fill=face, width=2)
        canvas.create_line(x + 3, y + 9, x + 15, y + 9, fill=face, width=2)
    elif style == "sad":
        canvas.create_line(x, y + 13, x + 20, y + 8, fill=face, width=2)
        canvas.create_oval(x + 7, y + 6, x + 13, y + 12, fill=face, outline=face)
    elif style == "angry":
        canvas.create_line(x, y + 2, x + 20, y + 8, fill=face, width=2)
        canvas.create_oval(x + 7, y + 8, x + 13, y + 14, fill=face, outline=face)
    elif style == "cross":
        canvas.create_line(x, y, x + 20, y + 16, fill=face, width=2)
        canvas.create_line(x + 20, y, x, y + 16, fill=face, width=2)
    else:
        canvas.create_oval(x, y, x + 18, y + 16, outline=face, width=2)
        canvas.create_oval(x + 7, y + 6, x + 11, y + 10, fill=face, outline=face)


def _draw_preview_mouth(canvas, style: str, face: str, dy: int = 0) -> None:
    if style == "smile":
        canvas.create_arc(78, 50 + dy, 114, 78 + dy, start=200, extent=140, outline=face, width=2)
    elif style == "small":
        canvas.create_line(88, 66 + dy, 104, 66 + dy, fill=face, width=2)
    elif style == "open":
        canvas.create_oval(84, 56 + dy, 108, 76 + dy, outline=face, width=2)
        canvas.create_line(88, 66 + dy, 104, 66 + dy, fill=face, width=2)
    elif style == "talk1":
        canvas.create_line(82, 60 + dy, 110, 60 + dy, fill=face, width=2)
        canvas.create_line(86, 68 + dy, 106, 68 + dy, fill=face, width=2)
    elif style == "talk2":
        canvas.create_rectangle(84, 58 + dy, 108, 72 + dy, outline=face, width=2)
    elif style == "sad":
        canvas.create_arc(78, 62 + dy, 114, 84 + dy, start=20, extent=140, outline=face, width=2)
    else:
        canvas.create_line(82, 66 + dy, 110, 66 + dy, fill=face, width=2)


def _preview_motion_delta(motion: str, frame: int) -> tuple[int, int]:
    if motion == "shake":
        return ((-3, 3, -2, 2)[frame % 4], 0)
    if motion == "bounce":
        return (0, (0, -3, -1, 2, 0)[frame % 5])
    if motion in {"bob", "blink", "talk"}:
        return (0, (0, -2, 0, 2)[frame % 4])
    return (0, 0)


def _preview_eye_for_motion(style: str, motion: str, frame: int) -> str:
    if motion == "blink" and frame % 8 == 4 and style not in {"cross", "angry"}:
        return "blink"
    if motion in {"bob", "bounce"} and frame % 12 == 6 and style not in {"cross", "angry"}:
        return "blink"
    return style


def _preview_mouth_for_motion(style: str, motion: str, frame: int) -> str:
    if motion == "talk":
        return ("talk1", "talk2", "open", "small")[frame % 4]
    return style


def _preview_text(text: object, limit: int = 16) -> str:
    printable = "".join(ch for ch in str(text) if " " <= ch <= "~")
    return printable[:limit]


def _print_help(stdout: TextIO) -> None:
    stdout.write(
        "JKS Voice Agent\n"
        "\n"
        "Usage:\n"
        "  python -m jks [--help]\n"
        "\n"
        "Environment:\n"
        "  JKS_AGENT_MODE      local, http, or ssh agent transport\n"
        "  JKS_AGENT_COMMAND   Local Hermes / Grantly command when mode=local\n"
        "  JKS_AGENT_ENDPOINT  Optional Hermes / Gran agent HTTP endpoint\n"
        "  JKS_STT_ENDPOINT    Speech-to-text endpoint\n"
        "  JKS_TTS_ENDPOINT    Text-to-speech endpoint\n"
        "  JKS_OLED_PORT       OLED serial port\n"
    )


def main(argv: Optional[Sequence[str]] = None, stdout: TextIO = sys.stdout) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]
    if "--help" in args or "-h" in args:
        _print_help(stdout)
        return 0

    root = tk.Tk()
    JksApp(root)
    root.mainloop()
    return 0
