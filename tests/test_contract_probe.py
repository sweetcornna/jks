import io
import json
import os
import unittest
from unittest.mock import patch

from tools.jks_contract_probe import main
from tools.jks_fake_services import start_fake_services


class ContractProbeTests(unittest.TestCase):
    def test_missing_config_returns_redacted_preflight_failure_without_probing(self):
        stdout = io.StringIO()

        with patch.dict(os.environ, {}, clear=True):
            exit_code = main([], stdout=stdout)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["checks"], {})
        self.assertIn("JKS_AGENT_ENDPOINT", payload["preflight"]["missing"])

    def test_probe_uses_configured_fake_services_and_prints_compact_json(self):
        server = start_fake_services()
        stdout = io.StringIO()
        try:
            env = {
                "JKS_AGENT_ENDPOINT": server.base_url + "/chat?token=secret",
                "JKS_AGENT_TOKEN": "secret-token",
                "JKS_STT_ENDPOINT": server.base_url + "/stt?api_key=secret",
                "JKS_TTS_ENDPOINT": server.base_url + "/tts?api_key=secret",
            }

            with patch.dict(os.environ, env, clear=True):
                exit_code = main([], stdout=stdout)
        finally:
            server.stop()

        text = stdout.getvalue()
        payload = json.loads(text)
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertNotIn("secret-token", text)
        self.assertNotIn("api_key=secret", text)
        self.assertNotIn(": ", text)
        self.assertEqual(payload["checks"]["agent"]["mode"], "http")
        self.assertGreater(payload["checks"]["agent"]["text_length"], 0)
        self.assertEqual(payload["checks"]["speech"]["stt_text_length"], len("hello agent"))
        self.assertGreater(payload["checks"]["speech"]["tts_bytes"], 0)
        self.assertEqual([event["kind"] for event in server.events], ["chat", "stt", "tts"])


if __name__ == "__main__":
    unittest.main()
