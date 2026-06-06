import io
import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from tools.jks_config_check import main


@contextmanager
def clean_cwd():
    old_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            yield
        finally:
            os.chdir(old_cwd)


class ConfigCheckCliTests(unittest.TestCase):
    def test_main_prints_compact_redacted_json(self):
        env = {
            "JKS_AGENT_ENDPOINT": "http://127.0.0.1:8787/chat",
            "JKS_AGENT_TOKEN": "secret-token",
            "JKS_STT_ENDPOINT": "http://127.0.0.1:8788/stt",
            "JKS_TTS_ENDPOINT": "http://127.0.0.1:8788/tts",
        }
        output = io.StringIO()

        with clean_cwd(), patch.dict(os.environ, env, clear=True):
            exit_code = main([], stdout=output)

        self.assertEqual(exit_code, 0)
        text = output.getvalue()
        self.assertNotIn("secret-token", text)
        self.assertIn("<redacted:12>", text)
        self.assertNotIn(": ", text)
        payload = json.loads(text)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["agent"]["token"], "<redacted:12>")

    def test_main_returns_one_when_required_agent_endpoint_is_missing(self):
        output = io.StringIO()

        with clean_cwd(), patch.dict(os.environ, {}, clear=True):
            exit_code = main([], stdout=output)

        self.assertEqual(exit_code, 1)
        payload = json.loads(output.getvalue())
        self.assertFalse(payload["ok"])
        self.assertIn("JKS_AGENT_ENDPOINT", payload["missing"])

    def test_main_returns_one_when_agent_endpoint_has_fake_speech(self):
        output = io.StringIO()

        with clean_cwd(), patch.dict(
            os.environ,
            {"JKS_AGENT_ENDPOINT": "http://127.0.0.1:8787/chat"},
            clear=True,
        ):
            exit_code = main([], stdout=output)

        self.assertEqual(exit_code, 1)
        payload = json.loads(output.getvalue())
        self.assertFalse(payload["ok"])
        self.assertFalse(payload["ready_for_real"])
        self.assertEqual(payload["speech"]["mode"], "fake")
        self.assertIn("JKS_STT_ENDPOINT", payload["missing"])
        self.assertIn("JKS_TTS_ENDPOINT", payload["missing"])

    def test_main_returns_one_when_dotenv_contains_placeholders(self):
        output = io.StringIO()

        with clean_cwd(), patch.dict(os.environ, {}, clear=True):
            Path(".env").write_text(
                "\n".join(
                    [
                        "JKS_AGENT_ENDPOINT=replace-with-agent-endpoint",
                        "JKS_STT_ENDPOINT=replace-with-stt-endpoint",
                        "JKS_TTS_ENDPOINT=replace-with-tts-endpoint",
                    ]
                )
            )
            exit_code = main([], stdout=output)

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertFalse(payload["ready_for_real"])
        self.assertIn("placeholder values must be replaced before real integration", payload["warnings"])

    def test_main_prints_json_when_config_loading_fails(self):
        output = io.StringIO()

        with clean_cwd(), patch.dict(os.environ, {"JKS_OLED_BAUD": "fast"}, clear=True):
            exit_code = main([], stdout=output)

        self.assertEqual(exit_code, 1)
        payload = json.loads(output.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errors"][0]["error"], "config")
        self.assertIn("JKS_OLED_BAUD", payload["errors"][0]["message"])


if __name__ == "__main__":
    unittest.main()
