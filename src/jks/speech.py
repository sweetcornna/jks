from __future__ import annotations

from pathlib import Path
import tempfile
from uuid import uuid4

import requests


FISH_ASR_ENDPOINT = "https://api.fish.audio/v1/asr"
FISH_TTS_ENDPOINT = "https://api.fish.audio/v1/tts"


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
    def __init__(
        self,
        stt_endpoint: str,
        tts_endpoint: str,
        output_dir: Path,
        stt_token: str = "",
        tts_token: str = "",
    ):
        self.stt_endpoint = stt_endpoint
        self.tts_endpoint = tts_endpoint
        self.output_dir = Path(output_dir)
        self.stt_token = stt_token
        self.tts_token = tts_token

    def transcribe(self, audio_path: Path) -> str:
        if not self.stt_endpoint:
            raise RuntimeError("JKS_STT_ENDPOINT is not configured")
        try:
            kwargs = {"files": None, "timeout": 60}
            with Path(audio_path).open("rb") as audio:
                kwargs["files"] = {"audio": audio}
                if self.stt_token:
                    kwargs["headers"] = {"Authorization": f"Bearer {self.stt_token}"}
                response = requests.post(self.stt_endpoint, **kwargs)
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
            kwargs = {
                "json": {"text": text, "voice": voice},
                "timeout": 60,
            }
            if self.tts_token:
                kwargs["headers"] = {"Authorization": f"Bearer {self.tts_token}"}
            response = requests.post(
                self.tts_endpoint,
                **kwargs,
            )
            response.raise_for_status()
        except Exception as exc:
            raise SpeechProviderError("text-to-speech request failed") from exc

        return _write_audio_output(self.output_dir, response.content, ".wav")


class FishAudioSpeechClient:
    def __init__(
        self,
        api_key: str,
        output_dir: Path,
        stt_endpoint: str = FISH_ASR_ENDPOINT,
        tts_endpoint: str = FISH_TTS_ENDPOINT,
        tts_model: str = "s2-pro",
        tts_latency: str = "low",
    ):
        self.api_key = api_key
        self.output_dir = Path(output_dir)
        self.stt_endpoint = stt_endpoint or FISH_ASR_ENDPOINT
        self.tts_endpoint = tts_endpoint or FISH_TTS_ENDPOINT
        self.tts_model = tts_model or "s2-pro"
        self.tts_latency = tts_latency or "low"

    def transcribe(self, audio_path: Path) -> str:
        if not self.api_key:
            raise RuntimeError("JKS_FISH_API_KEY is not configured")
        try:
            with Path(audio_path).open("rb") as audio:
                response = requests.post(
                    self.stt_endpoint,
                    files={"audio": audio},
                    data={"ignore_timestamps": "true"},
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=60,
                )
            response.raise_for_status()
        except Exception as exc:
            raise SpeechProviderError("fish speech-to-text request failed") from exc

        try:
            payload = response.json()
            text = payload["text"]
            if text is None:
                raise ValueError("text was null")
            return str(text)
        except Exception as exc:
            raise SpeechProviderError("fish speech-to-text response did not contain text") from exc

    def synthesize(self, text: str, voice: str) -> Path:
        if not self.api_key:
            raise RuntimeError("JKS_FISH_API_KEY is not configured")

        response = self._post_tts_stream(text, voice)

        try:
            chunks = _response_audio_chunks(response)
            return _write_streaming_audio_output(self.output_dir, chunks, ".mp3")
        finally:
            close = getattr(response, "close", None)
            if close is not None:
                close()

    def synthesize_and_play(self, text: str, voice: str, player) -> None:
        play_stream = getattr(player, "play_stream", None)
        if not callable(play_stream):
            audio_reply = self.synthesize(text, voice)
            player.play(audio_reply)
            return None

        response = self._post_tts_stream(text, voice)
        try:
            play_stream(_response_audio_chunks(response), suffix=".mp3")
        finally:
            close = getattr(response, "close", None)
            if close is not None:
                close()
        return None

    def _post_tts_stream(self, text: str, voice: str):
        if not self.api_key:
            raise RuntimeError("JKS_FISH_API_KEY is not configured")

        body = {
            "text": text,
            "format": "mp3",
            "latency": self.tts_latency,
            "chunk_length": 100,
            "min_chunk_length": 0,
        }
        if voice and voice != "default":
            body["reference_id"] = voice

        try:
            response = requests.post(
                self.tts_endpoint,
                json=body,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "model": self.tts_model,
                },
                timeout=60,
                stream=True,
            )
            response.raise_for_status()
            return response
        except Exception as exc:
            raise SpeechProviderError("fish text-to-speech request failed") from exc


def build_speech_client(config, output_dir: Path):
    stt_provider = config.stt_provider.lower()
    tts_provider = config.tts_provider.lower()
    if stt_provider == "fish" and tts_provider == "fish":
        return FishAudioSpeechClient(
            api_key=config.fish_api_key,
            output_dir=output_dir,
            stt_endpoint=config.stt_endpoint or FISH_ASR_ENDPOINT,
            tts_endpoint=config.tts_endpoint or FISH_TTS_ENDPOINT,
            tts_model=config.fish_tts_model,
            tts_latency=getattr(config, "fish_tts_latency", "low"),
        )
    if config.stt_endpoint and config.tts_endpoint:
        return HttpSpeechClient(
            config.stt_endpoint,
            config.tts_endpoint,
            output_dir,
            stt_token=config.stt_token,
            tts_token=config.tts_token,
        )
    if not config.stt_endpoint and not config.tts_endpoint:
        return FakeSpeechClient("hello agent")
    raise ValueError("JKS_STT_ENDPOINT and JKS_TTS_ENDPOINT must be configured together")


def _write_audio_output(output_dir: Path, content: bytes, suffix: str) -> Path:
    try:
        if not content:
            raise ValueError("empty audio response")
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / f"tts-output-{uuid4().hex}{suffix}"
        output.write_bytes(content)
        return output
    except Exception as exc:
        raise SpeechProviderError("text-to-speech output write failed") from exc


def _response_audio_chunks(response) -> object:
    iter_content = getattr(response, "iter_content", None)
    if iter_content is None:
        return (getattr(response, "content", b""),)
    return iter_content(chunk_size=8192)


def _write_streaming_audio_output(output_dir: Path, chunks, suffix: str) -> Path:
    try:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / f"tts-output-{uuid4().hex}{suffix}"
        bytes_written = 0
        with output.open("wb") as audio:
            for chunk in chunks:
                if not chunk:
                    continue
                audio.write(chunk)
                bytes_written += len(chunk)
        if bytes_written <= 0:
            raise ValueError("empty audio response")
        return output
    except Exception as exc:
        raise SpeechProviderError("text-to-speech output write failed") from exc
