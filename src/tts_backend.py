"""Pretrained neural text-to-speech backend (Kokoro-82M, via the
kokoro-onnx package - MIT-licensed wrapper, Apache-2.0-licensed model
weights - see https://github.com/thewh1teagle/kokoro-onnx).

Deliberately mirrors stt_backend.py's optional-dependency,
is_available()-gated pattern: kokoro_onnx (and the pretrained model
files it needs - NOT committed to this repository, see README.md for
how to download them) may not be installed/present, and that is a
normal, expected, non-error condition here, never a crash. voice.py is
the only caller, and falls back to the original pyttsx3 (SAPI5) engine
on ANY failure from this module - a missing dependency, missing model
files, or a synthesis/playback error - so a problem here can never
stop JARVIS from speaking (see voice.Voice.speak()).

Offline only: no network call is ever made by this module (the model
files, once downloaded, are read from local disk). No new audio-
playback dependency - synthesized audio is written to a temporary WAV
file and played back via the stdlib `winsound` module (Windows-only,
matching every other low-level module in this project - input_control.
py, window_control.py, screen_control.py are all already Windows-
specific). The temporary file is always removed afterward, including
on failure, and is never a file this project writes into git-tracked
storage.
"""

import os
import tempfile
import wave

import config

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Pretrained model files - NOT committed to git (see .gitignore's
# "models/" entry and README.md for the download instructions/URLs).
MODEL_PATH = os.path.join(_PROJECT_ROOT, "models", "tts", "kokoro-v1.0.onnx")
VOICES_PATH = os.path.join(_PROJECT_ROOT, "models", "tts", "voices-v1.0.bin")

SAMPLE_RATE_HZ = 24000  # Kokoro's fixed output sample rate.


class KokoroBackend:
    """Wraps kokoro_onnx.Kokoro. Lazily loads the ONNX model (imports
    kokoro_onnx, builds the onnxruntime InferenceSession) on first use
    - not at __init__ time - so simply constructing a KokoroBackend
    (e.g. only to call is_available()) never pays the ~1-2 second
    model-load cost and never requires the dependency to be installed
    at all.
    """

    name = "kokoro"

    def __init__(self):
        self._kokoro = None

    def is_available(self):
        """True if kokoro_onnx is installed AND both pretrained model
        files are present on disk. Never raises - any unexpected error
        while checking is treated as "not available", the same fail-
        closed policy stt_backend.OfflineWhisperBackend.is_available()
        already uses."""

        try:
            import kokoro_onnx  # noqa: F401
            return os.path.isfile(MODEL_PATH) and os.path.isfile(VOICES_PATH)
        except Exception:
            return False

    def _load(self):
        """Build (once) and cache the Kokoro instance, with the ONNX
        execution provider chosen from config.TTS_DEVICE. "cuda" is
        attempted via CUDAExecutionProvider with CPUExecutionProvider
        listed as a fallback in the same providers list - onnxruntime
        itself falls back silently (a console warning, not an
        exception) if the CUDA provider can't actually load on this
        machine (e.g. the NVIDIA cuBLAS/cuDNN runtime isn't installed -
        see config.TTS_DEVICE's own comment, the same documented,
        already-encountered situation as config.OFFLINE_STT_DEVICE for
        faster-whisper), so this is safe to attempt unconditionally."""

        if self._kokoro is not None:
            return self._kokoro

        import onnxruntime
        from kokoro_onnx import Kokoro

        providers = (
            ["CUDAExecutionProvider", "CPUExecutionProvider"]
            if config.TTS_DEVICE == "cuda"
            else ["CPUExecutionProvider"]
        )

        session = onnxruntime.InferenceSession(MODEL_PATH, providers=providers)
        self._kokoro = Kokoro.from_session(session, VOICES_PATH)

        return self._kokoro

    def synthesize(self, text, voice, speed):
        """Return (samples, sample_rate) - `samples` is a 1-D float32
        numpy array in [-1, 1]. Never plays or writes anything to disk
        - see speak() for that."""

        kokoro = self._load()

        return kokoro.create(text, voice=voice, speed=speed, lang="en-us")

    def speak(self, text, voice, speed, volume):
        """Synthesize and play `text` synchronously - blocks until
        playback finishes, matching voice.Voice.speak()'s existing
        pyttsx3-based blocking contract exactly (see that module's own
        docstring for why this project keeps speech synchronous)."""

        samples, sample_rate = self.synthesize(text, voice, speed)

        _play(samples, sample_rate, volume)


def _play(samples, sample_rate, volume):
    """Write `samples` to a temporary WAV file and play it back
    synchronously via the stdlib `winsound` module, then always delete
    the file - no new audio-playback dependency, and no audio file is
    ever left behind (never a file this project would accidentally
    commit)."""

    import numpy as np
    import winsound

    volume = max(0.0, min(1.0, volume))
    clipped = np.clip(samples * volume, -1.0, 1.0)
    pcm16 = (clipped * 32767).astype(np.int16)

    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)

    try:
        with wave.open(path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm16.tobytes())

        winsound.PlaySound(path, winsound.SND_FILENAME)

    finally:
        try:
            os.remove(path)
        except OSError:
            pass
