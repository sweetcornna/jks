import io
import json
import os
import unittest
from unittest.mock import patch

from tools.jks_config_check import main


class ConfigCheckCliTests(unittest.TestCase):
    def test_main_prints_compact_redacted_json(self):
        env = {
            "JKS_AGENT_ENDPOINT": "http://127.0.0.1:8787/chat",
            "JKS_AGENT_TOKEN": "secret-token",
            "JKS_STT_ENDPOINT": "http://127.0.0.1:8788/stt",
            "JKS_TTS_ENDPOINT": "http://127.0.0.1:8788/tts",
        }
        output = io.StringIO()

        with patch.dict(os.environ, env, clear=True):
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

        with patch.dict(os.environ, {}, clear=True):
            exit_code = main([], stdout=output)

        self.assertEqual(exit_code, 1)
        payload = json.loads(output.getvalue())
        self.assertFalse(payload["ok"])
        self.assertIn("JKS_AGENT_ENDPOINT", payload["missing"])

    def test_main_prints_json_when_config_loading_fails(self):
        output = io.StringIO()

        with patch.dict(os.environ, {"JKS_OLED_BAUD": "fast"}, clear=True):
            exit_code = main([], stdout=output)

        self.assertEqual(exit_code, 1)
        payload = json.loads(output.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errors"][0]["error"], "config")
        self.assertIn("JKS_OLED_BAUD", payload["errors"][0]["message"])


if __name__ == "__main__":
    unittest.main()
