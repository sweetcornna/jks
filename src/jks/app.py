from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, Sequence, TextIO

from .agent import HttpAgentClient
from .audio import AudioPlayer, AudioRecorder
from .config import AppConfig, load_config
from .display import DisplayController, NullDisplayController, open_serial_output
from .orchestrator import ConversationOrchestrator
from .speech import FakeSpeechClient, HttpSpeechClient


def build_orchestrator(
    config: AppConfig,
    *,
    open_serial: Callable[[str, int], object] = open_serial_output,
    output_dir: Optional[Path] = None,
    recorder=None,
    player=None,
) -> ConversationOrchestrator:
    output_dir = Path(output_dir) if output_dir is not None else Path(tempfile.gettempdir())

    try:
        serial_output = open_serial(config.oled_port, config.oled_baud)
        display = DisplayController(serial_output)
    except Exception:
        display = NullDisplayController()

    if config.stt_endpoint and config.tts_endpoint:
        speech = HttpSpeechClient(config.stt_endpoint, config.tts_endpoint, output_dir)
    elif not config.stt_endpoint and not config.tts_endpoint:
        speech = FakeSpeechClient("hello agent")
    else:
        raise ValueError("JKS_STT_ENDPOINT and JKS_TTS_ENDPOINT must be configured together")

    return ConversationOrchestrator(
        recorder=recorder or AudioRecorder(),
        speech=speech,
        agent=HttpAgentClient(config.agent_endpoint, config.agent_token),
        display=display,
        player=player or AudioPlayer(),
        voice=config.tts_voice,
    )


class JksApp:
    def __init__(self, root: tk.Tk, orchestrator: Optional[ConversationOrchestrator] = None):
        self.root = root
        self.root.title("JKS Voice Agent")
        self.status = tk.StringVar(value="Ready")
        self.transcript = tk.StringVar(value="")
        self.orchestrator = orchestrator or build_orchestrator(load_config())

        self.button = ttk.Button(root, text="Speak", command=self.start_turn)
        self.button.pack(padx=16, pady=12)
        ttk.Label(root, textvariable=self.status).pack(padx=16, pady=4)
        ttk.Label(root, textvariable=self.transcript, wraplength=420).pack(padx=16, pady=12)

    def start_turn(self) -> None:
        self.button.configure(state="disabled")
        self.status.set("Listening")
        thread = threading.Thread(target=self._run_turn, daemon=True)
        thread.start()

    def _run_turn(self) -> None:
        try:
            result = self.orchestrator.run_voice_turn()
        except Exception as exc:
            self.root.after(0, lambda exc=exc: self._finish_error(exc))
            return
        self.root.after(0, lambda: self._finish_success(result.user_text, result.agent_text))

    def _finish_success(self, user_text: str, agent_text: str) -> None:
        self.status.set("Ready")
        self.transcript.set(f"You: {user_text}\nAgent: {agent_text}")
        self.button.configure(state="normal")

    def _finish_error(self, exc: Exception) -> None:
        self.status.set(f"Error: {exc}")
        self.button.configure(state="normal")


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
