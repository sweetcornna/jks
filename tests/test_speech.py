import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jks.speech import FakeSpeechClient, HttpSpeechClient, SpeechProviderError


class SpeechTests(unittest.TestCase):
    def test_fake_speech_client_is_deterministic(self):
        client = FakeSpeechClient(text="hello agent")

        self.assertEqual(client.transcribe(Path("input.wav")), "hello agent")
        output = client.synthesize("reply", "warm")

        self.assertTrue(output.exists())
        self.assertGreater(output.stat().st_size, 0)
        self.assertEqual(output.read_bytes()[:4], b"RIFF")

    def test_http_stt_uploads_audio_file_and_returns_text(self):
        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"text": "transcribed text"}

        def fake_post(endpoint, *, files, timeout):
            self.assertEqual(endpoint, "https://speech.test/stt")
            self.assertEqual(timeout, 60)
            uploaded = files["audio"]
            self.assertEqual(uploaded.name, str(audio_path))
            self.assertEqual(uploaded.read(), b"audio-bytes")
            return FakeResponse()

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "input.wav"
            audio_path.write_bytes(b"audio-bytes")

            with patch("jks.speech.requests.post", side_effect=fake_post) as post:
                client = HttpSpeechClient(
                    stt_endpoint="https://speech.test/stt",
                    tts_endpoint="https://speech.test/tts",
                    output_dir=Path(temp_dir),
                )

                result = client.transcribe(audio_path)

        self.assertEqual(result, "transcribed text")
        post.assert_called_once()

    def test_http_tts_posts_json_and_writes_unique_audio_files(self):
        class FakeResponse:
            content = b"audio-bytes"

            def raise_for_status(self):
                pass

            def json(self):
                return {"text": "ignored"}

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("jks.speech.requests.post", return_value=FakeResponse()) as post:
                client = HttpSpeechClient(
                    stt_endpoint="https://speech.test/stt",
                    tts_endpoint="https://speech.test/tts",
                    output_dir=Path(temp_dir),
                )
                first_output = client.synthesize("hello", "warm")
                second_output = client.synthesize("hello again", "warm")

            self.assertEqual(first_output.parent, Path(temp_dir))
            self.assertTrue(first_output.name.startswith("tts-output-"))
            self.assertTrue(first_output.name.endswith(".wav"))
            self.assertTrue(first_output.exists())
            self.assertEqual(first_output.read_bytes(), b"audio-bytes")
            self.assertEqual(second_output.parent, Path(temp_dir))
            self.assertTrue(second_output.name.startswith("tts-output-"))
            self.assertTrue(second_output.name.endswith(".wav"))
            self.assertTrue(second_output.exists())
            self.assertEqual(second_output.read_bytes(), b"audio-bytes")
            self.assertNotEqual(first_output, second_output)

        post.assert_any_call(
            "https://speech.test/tts",
            json={"text": "hello", "voice": "warm"},
            timeout=60,
        )
        post.assert_any_call(
            "https://speech.test/tts",
            json={"text": "hello again", "voice": "warm"},
            timeout=60,
        )
        self.assertEqual(post.call_count, 2)

    def test_stt_provider_failures_are_wrapped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "input.wav"
            audio_path.write_bytes(b"audio-bytes")
            client = HttpSpeechClient(
                stt_endpoint="https://speech.test/stt",
                tts_endpoint="https://speech.test/tts",
                output_dir=Path(temp_dir),
            )

            with patch("jks.speech.requests.post", side_effect=OSError("offline")):
                with self.assertRaises(SpeechProviderError):
                    client.transcribe(audio_path)

    def test_stt_json_and_key_failures_are_wrapped(self):
        class InvalidJsonResponse:
            def raise_for_status(self):
                pass

            def json(self):
                raise ValueError("not json")

        class MissingTextResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"message": "missing text"}

        class NullTextResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"text": None}

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "input.wav"
            audio_path.write_bytes(b"audio-bytes")
            client = HttpSpeechClient(
                stt_endpoint="https://speech.test/stt",
                tts_endpoint="https://speech.test/tts",
                output_dir=Path(temp_dir),
            )

            with patch("jks.speech.requests.post", return_value=InvalidJsonResponse()):
                with self.assertRaises(SpeechProviderError):
                    client.transcribe(audio_path)

            with patch("jks.speech.requests.post", return_value=MissingTextResponse()):
                with self.assertRaises(SpeechProviderError):
                    client.transcribe(audio_path)

            with patch("jks.speech.requests.post", return_value=NullTextResponse()):
                with self.assertRaises(SpeechProviderError):
                    client.transcribe(audio_path)

    def test_stt_audio_file_failures_are_wrapped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = HttpSpeechClient(
                stt_endpoint="https://speech.test/stt",
                tts_endpoint="https://speech.test/tts",
                output_dir=Path(temp_dir),
            )

            with self.assertRaises(SpeechProviderError):
                client.transcribe(Path(temp_dir) / "missing.wav")

    def test_tts_provider_failures_are_wrapped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = HttpSpeechClient(
                stt_endpoint="https://speech.test/stt",
                tts_endpoint="https://speech.test/tts",
                output_dir=Path(temp_dir),
            )

            with patch("jks.speech.requests.post", side_effect=OSError("offline")):
                with self.assertRaises(SpeechProviderError):
                    client.synthesize("hello", "warm")

    def test_tts_file_failures_are_wrapped(self):
        class FakeResponse:
            content = b"audio-bytes"

            def raise_for_status(self):
                pass

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "not-a-directory"
            output_dir.write_text("occupied")
            client = HttpSpeechClient(
                stt_endpoint="https://speech.test/stt",
                tts_endpoint="https://speech.test/tts",
                output_dir=output_dir,
            )

            with patch("jks.speech.requests.post", return_value=FakeResponse()):
                with self.assertRaises(SpeechProviderError):
                    client.synthesize("hello", "warm")

    def test_missing_stt_endpoint_fails_before_network_call(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "input.wav"
            audio_path.write_bytes(b"audio-bytes")
            client = HttpSpeechClient(
                stt_endpoint="",
                tts_endpoint="https://speech.test/tts",
                output_dir=Path(temp_dir),
            )

            with patch("jks.speech.requests.post") as post:
                with self.assertRaises(RuntimeError):
                    client.transcribe(audio_path)

        post.assert_not_called()

    def test_missing_tts_endpoint_fails_before_network_call(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            client = HttpSpeechClient(
                stt_endpoint="https://speech.test/stt",
                tts_endpoint="",
                output_dir=Path(temp_dir),
            )

            with patch("jks.speech.requests.post") as post:
                with self.assertRaises(RuntimeError):
                    client.synthesize("hello", "warm")

        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
