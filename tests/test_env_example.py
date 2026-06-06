from pathlib import Path
import unittest


REQUIRED_KEYS = (
    "JKS_AGENT_HOST",
    "JKS_AGENT_USER",
    "JKS_AGENT_AUTH_METHOD",
    "JKS_AGENT_ENDPOINT",
    "JKS_AGENT_TOKEN",
    "JKS_STT_PROVIDER",
    "JKS_STT_ENDPOINT",
    "JKS_STT_TOKEN",
    "JKS_TTS_PROVIDER",
    "JKS_TTS_ENDPOINT",
    "JKS_TTS_TOKEN",
    "JKS_TTS_VOICE",
    "JKS_FISH_API_KEY",
    "JKS_FISH_TTS_MODEL",
    "JKS_OLED_PORT",
    "JKS_OLED_BAUD",
)


class EnvExampleTests(unittest.TestCase):
    def test_env_example_documents_required_keys_without_real_secrets(self):
        env_example = Path(".env.example")
        self.assertTrue(env_example.exists(), ".env.example should exist")
        text = env_example.read_text()

        for key in REQUIRED_KEYS:
            self.assertIn(key + "=", text)

        for forbidden in ("Bearer ", "root", "Qq", "secret-token", "password"):
            self.assertNotIn(forbidden, text)

        self.assertIn("replace-with-", text)


if __name__ == "__main__":
    unittest.main()
