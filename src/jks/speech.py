from __future__ import annotations

from pathlib import Path
import tempfile
from uuid import uuid4

import requests


class SpeechProviderError(RuntimeError):
    """Raised when an STT or TTS provider fails after configuration is valid."""


class FakeSpeechClient:
    def __init__(self, text: str = "hello"):
        self.text = text
        self.output_dir = Path(tempfile.gettempdir())

    def transcribe(self, audio_path: Path) -> str:
        return self.text

    def synthesize(self, text: str, voice: str) -> Path:
        output = self.output_dir / "jks-fake-tts.wav"
        output.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt ")
        return output


class HttpSpeechClient:
    def __init__(self, stt_endpoint: str, tts_endpoint: str, output_dir: Path):
        self.stt_endpoint = stt_endpoint
        self.tts_endpoint = tts_endpoint
        self.output_dir = Path(output_dir)

    def transcribe(self, audio_path: Path) -> str:
        if not self.stt_endpoint:
            raise RuntimeError("JKS_STT_ENDPOINT is not configured")
        try:
            with Path(audio_path).open("rb") as audio:
                response = requests.post(self.stt_endpoint, files={"audio": audio}, timeout=60)
            response.raise_for_status()
        except Exception as exc:
            raise SpeechProviderError("speech-to-text request failed") from exc

        try:
            payload = response.json()
            text = payload["text"]
            if text is None:
                raise ValueError("text was null")
            return str(text)
        except Exception as exc:
            raise SpeechProviderError("speech-to-text response did not contain text") from exc

    def synthesize(self, text: str, voice: str) -> Path:
        if not self.tts_endpoint:
            raise RuntimeError("JKS_TTS_ENDPOINT is not configured")
        try:
            response = requests.post(
                self.tts_endpoint,
                json={"text": text, "voice": voice},
                timeout=60,
            )
            response.raise_for_status()
        except Exception as exc:
            raise SpeechProviderError("text-to-speech request failed") from exc

        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            output = self.output_dir / f"tts-output-{uuid4().hex}.wav"
            output.write_bytes(response.content)
            return output
        except Exception as exc:
            raise SpeechProviderError("text-to-speech output write failed") from exc
