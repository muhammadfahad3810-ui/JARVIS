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

import glob
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

# Phase 11.14: every temp WAV this module writes uses this recognizable
# prefix (see _play() below), so cleanup_orphaned_temp_files() can find
# and remove ONLY files this project created - never touching unrelated
# files that happen to already be in the OS temp directory.
TEMP_FILE_PREFIX = "jarvis_tts_"


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

    def warm_up(self):
        """Phase 11.14: force the model to load NOW rather than lazily
        on the first speak() call. Measured cold-load-plus-first-
        synthesis cost is ~2-3s (see the Phase 11.13 audit report) -
        without this, that cost lands on whatever the first real spoken
        response happens to be, which for most control modules speaks
        BEFORE performing the action (see e.g. keyboard_control.py),
        so an unlucky first command could feel sluggish. voice.Voice.
        __init__() calls this once, during JARVIS startup (alongside
        the existing microphone-calibration delay), so every actual
        command response only ever pays the warm (~0.7-1.5s) cost.
        Never raises internally, but does not catch anything itself -
        see voice.py's own try/except around this call, which treats a
        failure here as "this backend isn't usable this session" and
        falls back to pyttsx3 for the whole session, not just once."""

        self._load()

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

    def stop(self):
        """Stop any currently-playing Kokoro-synthesized audio. Safe to
        call at any time, including when nothing is playing (a no-op in
        that case) - see stop_playback()'s own docstring for why this
        is a clean, low-risk addition rather than a new threading/
        interruption framework."""

        stop_playback()


def stop_playback():
    """Immediately stop any sound currently playing via winsound (the
    mechanism _play() below uses) - a plain, stdlib-only wrapper around
    winsound's own SND_PURGE flag. Deliberately NOT wired into any new
    background-thread/async playback machinery: this project's speech
    stays synchronous (see voice.py's own docstring), so today nothing
    OTHER than the thread already blocked inside a speak() call could
    ever call this concurrently - it exists as a clean, always-safe
    primitive for a future caller (e.g. a signal handler) rather than
    solving a problem this phase's synchronous architecture actually
    has. Never raises."""

    import winsound

    try:
        winsound.PlaySound(None, winsound.SND_PURGE)
    except Exception:
        pass


def cleanup_orphaned_temp_files():
    """Best-effort removal of any TEMP_FILE_PREFIX-named WAV files left
    behind in the OS temp directory by a previous run that crashed (or
    was killed) between _play() writing the file and its own `finally:
    os.remove(path)` running. Normal operation already removes every
    temp file it creates (see _play()) - this is defense in depth
    against process-crash leaks, not a fix for a leak on the happy
    path. Never raises; a file that can't be removed (e.g. still locked
    by another process) is silently skipped, not retried."""

    pattern = os.path.join(tempfile.gettempdir(), TEMP_FILE_PREFIX + "*.wav")

    for path in glob.glob(pattern):
        try:
            os.remove(path)
        except OSError:
            pass


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

    fd, path = tempfile.mkstemp(prefix=TEMP_FILE_PREFIX, suffix=".wav")
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
