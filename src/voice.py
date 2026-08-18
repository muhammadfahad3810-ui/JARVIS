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

Phase 11.14 (interaction reliability), all additive, none of it changes
what any voice.speak(text) call site says or when it's called:

- The neural backend is warmed up (model loaded) once, here, at
  Voice.__init__() time - not lazily on the first spoken response - so
  the one-time ~2-3s model-load cost lands during JARVIS startup
  (alongside the existing microphone-calibration delay) instead of on
  whatever command happens to be spoken first. See tts_backend.
  KokoroBackend.warm_up().
- speak() serializes on a lock, so two responses can never play
  simultaneously - this also naturally makes speak() calls queue
  (the second caller's speak() blocks on the lock until the first
  finishes) without needing a separate worker thread/queue.Queue: this
  project's speech has always been synchronous, so a plain lock is the
  minimum mechanism that guarantees the "never overlapping" property
  even if a future change ever calls speak() from more than one thread.
- speak() suppresses an EXACT-text repeat within config.
  DUPLICATE_SPEECH_SUPPRESS_SECONDS (default 2s) - defense against an
  accidental double-dispatch producing the same response twice in a
  row, never a permanent suppression (a genuinely repeated command a
  few seconds later always speaks again).
- stop() (new) stops whatever is currently playing, safe to call at
  any time - see tts_backend.stop_playback()'s own docstring for why
  this stays a simple primitive rather than a new audio framework.
- Orphaned temp WAV files from a previous crashed run are swept once,
  here, at startup - see tts_backend.cleanup_orphaned_temp_files().

response text generation (every voice.speak(text) call site) is
completely unchanged by this phase - this module only ever receives an
already-decided string and speaks it; it never decides what to say.
"""

import threading
import time

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

        tts_backend.cleanup_orphaned_temp_files()

        self._neural_backend = _select_neural_backend()

        # Serializes speak() (see this module's own docstring) - a
        # plain, non-reentrant Lock, since no call path in this
        # codebase ever calls speak() from within another speak() call.
        self._speech_lock = threading.Lock()

        # Exact-text-repeat suppression state (see config.
        # DUPLICATE_SPEECH_SUPPRESS_SECONDS).
        self._last_spoken_text = None
        self._last_spoken_time = None

    def speak(self, text):

        print(f"JARVIS: {text}")

        with self._speech_lock:

            if self._is_recent_duplicate(text):
                return

            self._record_spoken(text)

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
                    # failure (synthesis error, playback error,
                    # anything) must never mean JARVIS stays silent.
                    pass

            self.engine.say(text)
            self.engine.runAndWait()

    def stop(self):
        """Stop whatever is currently being spoken, if anything -
        never raises, safe to call even when nothing is playing or
        when called from outside speak() (e.g. a future interrupt
        handler). See tts_backend.stop_playback()'s own docstring for
        why this project keeps this a simple, synchronous primitive
        rather than a new audio-interruption framework."""

        try:
            self.engine.stop()
        except Exception:
            pass

        if self._neural_backend is not None:
            try:
                self._neural_backend.stop()
            except Exception:
                pass

    def _is_recent_duplicate(self, text):

        if self._last_spoken_text != text or self._last_spoken_time is None:
            return False

        age = time.time() - self._last_spoken_time

        return age < config.DUPLICATE_SPEECH_SUPPRESS_SECONDS

    def _record_spoken(self, text):

        self._last_spoken_text = text
        self._last_spoken_time = time.time()


def _select_neural_backend():
    """Return a ready-to-use, WARMED-UP neural backend instance, or
    None if config.TTS_BACKEND doesn't name one, it reports itself
    unavailable (missing dependency or missing model files - both
    normal, non-error conditions - see tts_backend.KokoroBackend.
    is_available()), or warm_up() itself fails. Never raises: an
    unexpected error at any point here is treated as "unavailable", so
    a broken optional dependency can never prevent Voice.__init__()
    from succeeding - the whole session then simply uses pyttsx3, the
    same fallback behavior as before this backend existed at all."""

    if config.TTS_BACKEND == "kokoro":

        backend = tts_backend.KokoroBackend()

        try:
            if backend.is_available():
                backend.warm_up()
                return backend
        except Exception:
            pass

    return None
