from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
from typing import Optional
from uuid import uuid4


class AudioRecorder:
    def __init__(
        self,
        sample_rate: int = 16000,
        output_dir: Optional[Path] = None,
        sounddevice_module=None,
        soundfile_module=None,
    ):
        self.sample_rate = sample_rate
        self.output_dir = Path(output_dir) if output_dir is not None else Path(tempfile.gettempdir())
        self._sounddevice_module = sounddevice_module
        self._soundfile_module = soundfile_module
        self._stream = None
        self._chunks = []

    def record_fixed_seconds(self, seconds: float = 4.0) -> Path:
        if seconds <= 0:
            raise ValueError("seconds must be positive")
        sd = self._sounddevice()
        sf = self._soundfile()
        frames = int(self.sample_rate * seconds)
        data = sd.rec(frames, samplerate=self.sample_rate, channels=1, dtype="float32")
        sd.wait()
        output = self._new_output_path()
        sf.write(output, data, self.sample_rate)
        return output

    def start_recording(self) -> None:
        if self._stream is not None:
            raise RuntimeError("recording already in progress")
        self._chunks = []
        stream = self._sounddevice().InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            callback=self._capture_chunk,
        )
        try:
            stream.start()
        except Exception:
            stream.close()
            raise
        self._stream = stream

    def stop_recording(self) -> Path:
        if self._stream is None:
            raise RuntimeError("recording is not in progress")
        stream = self._stream
        self._stream = None
        try:
            stream.stop()
        finally:
            stream.close()

        output = self._new_output_path()
        self._soundfile().write(output, self._merged_chunks(), self.sample_rate)
        return output

    def _capture_chunk(self, indata, frames, time, status) -> None:
        if hasattr(indata, "copy"):
            self._chunks.append(indata.copy())
        else:
            self._chunks.append(indata)

    def _merged_chunks(self):
        if not self._chunks:
            return []
        if len(self._chunks) == 1:
            return self._chunks[0]
        try:
            import numpy as np
        except ImportError:
            return self._chunks
        return np.concatenate(self._chunks, axis=0)

    def _new_output_path(self) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        return self.output_dir / f"jks-recording-{uuid4().hex}.wav"

    def _sounddevice(self):
        if self._sounddevice_module is None:
            import sounddevice as sd

            self._sounddevice_module = sd
        return self._sounddevice_module

    def _soundfile(self):
        if self._soundfile_module is None:
            import soundfile as sf

            self._soundfile_module = sf
        return self._soundfile_module


class AudioPlayer:
    def __init__(self, runner=subprocess.run):
        self._runner = runner

    def play(self, audio_path: Path) -> None:
        self._runner(["afplay", str(audio_path)], check=True)
