"""Text-to-speech facade - the single object every control module
speaks through (see each module's `voice.speak(text)` calls).

Phase 11.13: tries the configured neural backend first (see
tts_backend.py - currently Kokoro-82M) and falls back to the original
pyttsx3 (SAPI5) engine on ANY failure - the neural dependency/model
files aren't installed, or synthesis/playback raises for any reason -
so a problem with the neural backend can NEVER stop JARVIS from
speaking. With config.TTS_BACKEND set to anything other than "kokoro"
(or with the neural backend simply unavailable), behavior is byte-for-
byte identical to every phase before this one: pyttsx3 only, same
rate/volume properties, same synchronous print-then-speak contract.

response text generation (every voice.speak(text) call site) is
completely unchanged by this phase - this module only ever receives an
already-decided string and speaks it; it never decides what to say.
"""

import pyttsx3

import config
import tts_backend


class Voice:
    """Wraps pyttsx3 initialization (unchanged, still the fallback
    engine) and, when available, a neural TTS backend."""

    def __init__(self):

        self.engine = pyttsx3.init()
        self.engine.setProperty("rate", config.TTS_RATE)
        self.engine.setProperty("volume", config.TTS_VOLUME)

        self._neural_backend = _select_neural_backend()

    def speak(self, text):

        print(f"JARVIS: {text}")

        if self._neural_backend is not None:

            try:
                self._neural_backend.speak(
                    text,
                    voice=config.TTS_VOICE,
                    speed=config.TTS_SPEED,
                    volume=config.TTS_VOLUME,
                )
                return

            except Exception:
                # Fall through to pyttsx3 below - a neural-backend
                # failure (synthesis error, playback error, anything)
                # must never mean JARVIS stays silent.
                pass

        self.engine.say(text)
        self.engine.runAndWait()


def _select_neural_backend():
    """Return a ready-to-use neural backend instance, or None if
    config.TTS_BACKEND doesn't name one or it reports itself
    unavailable (missing dependency or missing model files - both
    normal, non-error conditions - see tts_backend.KokoroBackend.
    is_available()). Never raises: an unexpected error while checking
    availability is treated the same as "unavailable", so a broken
    optional dependency can never prevent Voice.__init__() from
    succeeding."""

    if config.TTS_BACKEND == "kokoro":

        backend = tts_backend.KokoroBackend()

        try:
            if backend.is_available():
                return backend
        except Exception:
            pass

    return None
