import io
import json
import os
import tempfile
import unittest
import wave
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from tools.jks_fake_services import start_fake_services
from tools.jks_turn_probe import main


@contextmanager
def clean_cwd():
    old_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            yield
        finally:
            os.chdir(old_cwd)


def write_silent_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x00\x00" * 400)


class TurnProbeCliTests(unittest.TestCase):
    def test_missing_audio_argument_returns_error_without_config_or_network_probe(self):
        stdout = io.StringIO()

        with clean_cwd(), patch.dict(os.environ, {}, clear=True):
            exit_code = main([], stdout=stdout)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["checks"], {})
        self.assertEqual(payload["errors"], [{"error": "audio", "message": "--audio is required"}])

    def test_missing_config_returns_preflight_without_network_probe(self):
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "input.wav"
            write_silent_wav(audio_path)

            with clean_cwd(), patch.dict(os.environ, {}, clear=True):
                with patch("jks.speech.requests.post") as speech_post:
                    with patch("jks.agent.requests.post") as agent_post:
                        exit_code = main(["--audio", str(audio_path)], stdout=stdout)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["checks"], {})
        self.assertEqual(payload["server_events"], [])
        self.assertIn("JKS_AGENT_ENDPOINT", payload["preflight"]["missing"])
        speech_post.assert_not_called()
        agent_post.assert_not_called()

    def test_probe_runs_stt_agent_tts_in_turn_order_and_redacts_secrets(self):
        server = start_fake_services()
        stdout = io.StringIO()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                audio_path = Path(temp_dir) / "input.wav"
                write_silent_wav(audio_path)
                env = {
                    "JKS_AGENT_ENDPOINT": server.base_url + "/chat?token=secret",
                    "JKS_AGENT_TOKEN": "secret-token",
                    "JKS_STT_ENDPOINT": server.base_url + "/stt?api_key=secret",
                    "JKS_TTS_ENDPOINT": server.base_url + "/tts?api_key=secret",
                    "JKS_TTS_VOICE": "warm",
                }

                with clean_cwd(), patch.dict(os.environ, env, clear=True):
                    exit_code = main(["--audio", str(audio_path)], stdout=stdout)
        finally:
            server.stop()

        text = stdout.getvalue()
        payload = json.loads(text)
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertNotIn("secret-token", text)
        self.assertNotIn("api_key=secret", text)
        self.assertNotIn("token=secret", text)
        self.assertNotIn(": ", text)
        self.assertNotIn("hello agent", text)
        self.assertNotIn("Fake reply to: hello agent", text)
        self.assertEqual(payload["checks"]["stt"], {"text_length": len("hello agent")})
        self.assertEqual(payload["checks"]["agent"]["text_length"], len("Fake reply to: hello agent"))
        self.assertEqual(payload["checks"]["agent"]["emotion"], "happy")
        self.assertGreater(payload["checks"]["tts"]["bytes"], 0)
        self.assertEqual(payload["checks"]["tts"]["voice"], "warm")
        self.assertEqual(payload["server_events"], ["stt", "chat", "tts"])
        self.assertEqual([event["kind"] for event in server.events], ["stt", "chat", "tts"])

    def test_verbose_probe_includes_transcripts_for_local_debugging(self):
        server = start_fake_services()
        stdout = io.StringIO()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                audio_path = Path(temp_dir) / "input.wav"
                write_silent_wav(audio_path)
                env = {
                    "JKS_AGENT_ENDPOINT": server.base_url + "/chat",
                    "JKS_STT_ENDPOINT": server.base_url + "/stt",
                    "JKS_TTS_ENDPOINT": server.base_url + "/tts",
                }

                with clean_cwd(), patch.dict(os.environ, env, clear=True):
                    exit_code = main(["--audio", str(audio_path), "--verbose"], stdout=stdout)
        finally:
            server.stop()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["checks"]["stt"]["text"], "hello agent")
        self.assertEqual(payload["checks"]["agent"]["text"], "Fake reply to: hello agent")

    def test_stt_failure_reports_stt_stage(self):
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "input.wav"
            write_silent_wav(audio_path)
            env = {
                "JKS_AGENT_ENDPOINT": "http://agent.local/chat",
                "JKS_STT_ENDPOINT": "http://speech.local/stt",
                "JKS_TTS_ENDPOINT": "http://speech.local/tts",
            }

            with clean_cwd(), patch.dict(os.environ, env, clear=True):
                with patch("jks.speech.requests.post", side_effect=OSError("offline")):
                    exit_code = main(["--audio", str(audio_path)], stdout=stdout)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["server_events"], [])
        self.assertEqual(payload["errors"][0]["error"], "stt")

    def test_play_flag_plays_generated_tts_audio(self):
        server = start_fake_services()
        stdout = io.StringIO()
        played = []
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                audio_path = Path(temp_dir) / "input.wav"
                write_silent_wav(audio_path)
                env = {
                    "JKS_AGENT_ENDPOINT": server.base_url + "/chat",
                    "JKS_STT_ENDPOINT": server.base_url + "/stt",
                    "JKS_TTS_ENDPOINT": server.base_url + "/tts",
                }

                with clean_cwd(), patch.dict(os.environ, env, clear=True):
                    with patch("jks.audio.AudioPlayer.play", side_effect=lambda path: played.append(Path(path))):
                        exit_code = main(["--audio", str(audio_path), "--play"], stdout=stdout)
        finally:
            server.stop()

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["checks"]["playback"], {"played": True})
        self.assertEqual(len(played), 1)
        self.assertTrue(played[0].exists())


if __name__ == "__main__":
    unittest.main()
