from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jks.config import AppConfig


class FakeRoot:
    def __init__(self):
        self.after_calls = []
        self.title_text = ""
        self.mainloop_called = False

    def title(self, text):
        self.title_text = text

    def after(self, delay_ms, callback):
        self.after_calls.append(delay_ms)
        callback()

    def mainloop(self):
        self.mainloop_called = True


class DelayedRoot(FakeRoot):
    def after(self, delay_ms, callback):
        self.after_calls.append((delay_ms, callback))


class FakeStringVar:
    def __init__(self, value=""):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


class FakeButton:
    def __init__(self, root, text, command):
        self.root = root
        self.text = text
        self.command = command
        self.options = {}
        self.packed = False

    def pack(self, **kwargs):
        self.packed = True

    def configure(self, **kwargs):
        self.options.update(kwargs)


class FakeLabel:
    def __init__(self, root, **kwargs):
        self.root = root
        self.kwargs = kwargs

    def pack(self, **kwargs):
        self.pack_kwargs = kwargs


class ImmediateThread:
    def __init__(self, target, daemon):
        self.target = target
        self.daemon = daemon

    def start(self):
        self.target()


class FakeOrchestrator:
    def __init__(self, result=None, exc=None):
        self.result = result
        self.exc = exc
        self.turns = 0

    def run_voice_turn(self):
        self.turns += 1
        if self.exc:
            raise self.exc
        return self.result


def sample_config(**overrides):
    data = {
        "agent_host": "",
        "agent_user": "",
        "agent_auth_method": "",
        "agent_endpoint": "",
        "agent_token": "",
        "stt_provider": "",
        "stt_endpoint": "",
        "tts_provider": "",
        "tts_endpoint": "",
        "tts_voice": "warm",
        "oled_port": "/dev/cu.missing",
        "oled_baud": 115200,
    }
    data.update(overrides)
    return AppConfig(**data)


class AppTests(unittest.TestCase):
    def test_importing_app_does_not_create_gui(self):
        import jks.app as app

        self.assertTrue(callable(app.main))

    def test_main_help_prints_usage_without_creating_gui(self):
        from jks import app

        created_roots = []
        with patch.object(app.tk, "Tk", side_effect=lambda: created_roots.append(FakeRoot())):
            output = io.StringIO()
            exit_code = app.main(["--help"], stdout=output)

        self.assertEqual(exit_code, 0)
        self.assertIn("JKS Voice Agent", output.getvalue())
        self.assertEqual(created_roots, [])

    def test_orchestrator_builder_uses_null_display_when_serial_unavailable(self):
        from jks import app
        from jks.display import NullDisplayController
        from jks.speech import FakeSpeechClient

        with tempfile.TemporaryDirectory() as tmp:
            config = sample_config()

            orchestrator = app.build_orchestrator(
                config,
                open_serial=lambda path, baud: (_ for _ in ()).throw(OSError("missing oled")),
                output_dir=Path(tmp),
            )

        self.assertIsInstance(orchestrator.display, NullDisplayController)
        self.assertIsInstance(orchestrator.speech, FakeSpeechClient)

    def test_orchestrator_builder_rejects_partial_speech_config(self):
        from jks import app

        with self.assertRaises(ValueError):
            app.build_orchestrator(
                sample_config(stt_endpoint="http://stt.local"),
                open_serial=lambda path, baud: io.BytesIO(),
            )

    def test_ui_success_turn_updates_transcript_and_restores_button(self):
        from jks import app
        from jks.orchestrator import TurnResult

        root = FakeRoot()
        orchestrator = FakeOrchestrator(
            result=TurnResult(user_text="hello", agent_text="reply", emotion="happy")
        )

        with patch.object(app.tk, "StringVar", FakeStringVar), patch.object(
            app.ttk, "Button", FakeButton
        ), patch.object(app.ttk, "Label", FakeLabel), patch.object(
            app.threading, "Thread", ImmediateThread
        ):
            ui = app.JksApp(root, orchestrator=orchestrator)
            ui.start_turn()

        self.assertEqual(orchestrator.turns, 1)
        self.assertEqual(ui.status.get(), "Ready")
        self.assertIn("You: hello", ui.transcript.get())
        self.assertIn("Agent: reply", ui.transcript.get())
        self.assertEqual(ui.button.options["state"], "normal")

    def test_ui_error_turn_restores_button(self):
        from jks import app

        root = FakeRoot()
        orchestrator = FakeOrchestrator(exc=RuntimeError("agent missing"))

        with patch.object(app.tk, "StringVar", FakeStringVar), patch.object(
            app.ttk, "Button", FakeButton
        ), patch.object(app.ttk, "Label", FakeLabel), patch.object(
            app.threading, "Thread", ImmediateThread
        ):
            ui = app.JksApp(root, orchestrator=orchestrator)
            ui.start_turn()

        self.assertIn("agent missing", ui.status.get())
        self.assertEqual(ui.button.options["state"], "normal")

    def test_ui_error_turn_preserves_exception_for_delayed_after_callback(self):
        from jks import app

        root = DelayedRoot()
        orchestrator = FakeOrchestrator(exc=RuntimeError("agent missing"))

        with patch.object(app.tk, "StringVar", FakeStringVar), patch.object(
            app.ttk, "Button", FakeButton
        ), patch.object(app.ttk, "Label", FakeLabel), patch.object(
            app.threading, "Thread", ImmediateThread
        ):
            ui = app.JksApp(root, orchestrator=orchestrator)
            ui.start_turn()

        root.after_calls[0][1]()

        self.assertIn("agent missing", ui.status.get())
        self.assertEqual(ui.button.options["state"], "normal")


if __name__ == "__main__":
    unittest.main()
