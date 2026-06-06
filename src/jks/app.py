from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, Sequence, TextIO

from .agent import build_agent_client
from .audio import AudioPlayer, AudioRecorder
from .config import AppConfig, load_config
from .display import DisplayController, NullDisplayController, open_serial_output
from .expression import TurnState
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
) -> ConversationOrchestrator:
    output_dir = Path(output_dir) if output_dir is not None else Path(tempfile.gettempdir())

    try:
        serial_output = open_serial(config.oled_port, config.oled_baud)
        display = DisplayController(serial_output)
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
    )


STATE_LABELS = {
    TurnState.IDLE: "Ready",
    TurnState.LISTENING: "Listening",
    TurnState.TRANSCRIBING: "Transcribing",
    TurnState.THINKING: "Thinking",
    TurnState.SPEAKING: "Speaking",
    TurnState.ERROR: "Error",
}


class JksApp:
    def __init__(self, root: tk.Tk, orchestrator: Optional[ConversationOrchestrator] = None):
        self.root = root
        self.root.title("JKS Voice Agent")
        self.status = tk.StringVar(value="Ready")
        self.device_status = tk.StringVar(value="OLED ready")
        self.transcript = tk.StringVar(value="")
        self.orchestrator = orchestrator or build_orchestrator(
            load_config(),
            status_callback=self._show_turn_state,
            display_status_callback=self._show_display_status,
            display_error_callback=self._show_display_status,
        )
        self._recording = False

        self.button = ttk.Button(root, text="Speak", command=self.start_turn)
        self.button.pack(padx=16, pady=12)
        ttk.Label(root, textvariable=self.status).pack(padx=16, pady=4)
        ttk.Label(root, textvariable=self.device_status, wraplength=420).pack(padx=16, pady=4)
        ttk.Label(root, textvariable=self.transcript, wraplength=420).pack(padx=16, pady=12)

    def start_turn(self) -> None:
        if not self._recording:
            self._start_recording()
            return

        self._stop_and_run_turn()

    def _start_recording(self) -> None:
        self.button.configure(state="disabled")
        self.status.set("Listening")
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
        self.root.after(
            0,
            lambda: self._finish_success(result.user_text, result.agent_text, result.audio_error),
        )

    def _finish_success(self, user_text: str, agent_text: str, audio_error: str = "") -> None:
        self._recording = False
        if audio_error:
            self.status.set(f"Voice output failed: {audio_error}")
        else:
            self.status.set("Ready")
        self.transcript.set(f"You: {user_text}\nAgent: {agent_text}")
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
        self.root.after(0, lambda label=label: self.status.set(label))

    def _show_display_status(self, message: str) -> None:
        self.root.after(0, lambda message=message: self.device_status.set(message))


def _print_help(stdout: TextIO) -> None:
    stdout.write(
        "JKS Voice Agent\n"
        "\n"
        "Usage:\n"
        "  python -m jks [--help]\n"
        "\n"
        "Environment:\n"
        "  JKS_AGENT_ENDPOINT  Remote Hermes / Gran agent HTTP endpoint\n"
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
