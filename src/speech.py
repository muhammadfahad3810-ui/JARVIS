import time

import speech_recognition as sr

import config
import stt_backend


def _new_diagnostics():
    """Phase 11.11 (Step 3): a fresh, all-fields-present diagnostics
    dict for one listen() call - see Speech.last_diagnostics' own
    docstring. Every key is always present (even when its stage never
    ran) so callers/tests never need a .get() with a default; a stage
    that never ran simply keeps its initial "did not happen" value.
    Deliberately distinguishes each of the six things Phase 11.11's
    investigation needed to tell apart:

        A. microphone captured useful speech -> "audio_captured"
        B. Google recognized speech            -> "google_result"
        C. Google returned SpeechUnintelligible -> "google_error"
           == "unintelligible"
        D. Whisper was invoked                 -> "whisper_invoked"
        E. Whisper returned useful speech       -> "whisper_result"
        F. Whisper hallucinated unrelated speech -> distinguished from
           E by "whisper_rejected_low_confidence" (only meaningful
           when config.ENABLE_WHISPER_CONFIDENCE_GATE is True - with it
           off, this module cannot itself tell a hallucination apart
           from a genuine low-volume/quiet recognition, since both
           produce non-empty text from Whisper's perspective; that is
           exactly the gap config.ENABLE_WHISPER_CONFIDENCE_GATE's own
           comment documents as needing live-tuned thresholds before
           being trusted to reject automatically).
    """

    return {
        "audio_captured": False,
        "capture_wall_time": None,
        "capture_audio_duration": None,
        "google_attempted": False,
        "google_result": None,
        "google_error": None,  # "unintelligible" | "network_error" | None
        "whisper_invoked": False,
        "whisper_result": None,
        "whisper_confidence": None,  # (avg_no_speech_prob, avg_logprob)
        "whisper_rejected_low_confidence": False,
        "urdu_attempted": False,
        "urdu_result": None,
        "final_result": "",
        "final_source": None,  # "google" | "urdu" | "offline_whisper" | None
    }


def _describe_microphone(source):
    """Phase 11.9 (Step 6) diagnostic helper: a short, human-readable
    description of the microphone `source` actually opened - device
    index and, if resolvable, its name. Never raises: if the device
    name can't be resolved for any reason (unsupported platform,
    PyAudio quirk, no default device), falls back to just the index.
    Never logs or persists any audio data - this is a scalar text
    description only, for config.DEBUG console output."""

    device_index = getattr(source, "device_index", None)

    if device_index is not None:

        try:
            names = sr.Microphone.list_microphone_names()

            if 0 <= device_index < len(names):
                return f"index={device_index} name={names[device_index]!r}"

        except Exception:
            pass

        return f"index={device_index}"

    # device_index is None -> PyAudio's own default input device was
    # used (see sr.Microphone.__init__) - resolve and show which one
    # that actually is, rather than just the word "default".
    try:
        import pyaudio

        pa = pyaudio.PyAudio()

        try:
            info = pa.get_default_input_device_info()
            return (
                f"index={info.get('index')} name={info.get('name')!r} "
                "(system default)"
            )
        finally:
            pa.terminate()

    except Exception:
        return "index=None (system default, name unresolved)"


def _audio_duration_seconds(audio):
    """Phase 11.9 (Step 6) diagnostic helper: the duration, in seconds,
    of a captured sr.AudioData clip, computed from its own declared
    sample rate/width - never from persisting or inspecting the actual
    waveform contents. Never raises: returns 0.0 if the duration can't
    be computed for any reason."""

    try:
        return len(audio.frame_data) / (
            audio.sample_width * audio.sample_rate
        )
    except Exception:
        return 0.0


class Speech:
    """Handles microphone input and speech-to-text recognition."""

    def __init__(self, voice):

        self.voice = voice

        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = config.ENERGY_THRESHOLD
        self.recognizer.dynamic_energy_threshold = config.DYNAMIC_ENERGY_THRESHOLD
        self.recognizer.pause_threshold = config.PAUSE_THRESHOLD
        self.recognizer.non_speaking_duration = config.NON_SPEAKING_DURATION

        # Phase 10.1: STT backend abstraction (stt_backend.py). The
        # online backend is unchanged from Phase 1-9. The offline
        # backend is a safe no-op until its optional dependency is
        # installed - see stt_backend.OfflineWhisperBackend.
        self.online_backend = stt_backend.GoogleOnlineBackend()
        self.offline_backend = stt_backend.OfflineWhisperBackend()

        # Phase 11.4: a second GoogleOnlineBackend instance, fixed to
        # the Urdu language code - unconditionally constructed (cheap,
        # no I/O, no network call at construction time - mirrors how
        # offline_backend above is already always constructed
        # regardless of config.OFFLINE_STT_ENABLED) but only ever
        # consulted from _try_urdu_fallback() when config.ENABLE_
        # URDU_STT_FALLBACK is True - see _recognize() below.
        self.urdu_online_backend = stt_backend.GoogleOnlineBackend(
            language=config.URDU_RECOGNITION_LANGUAGE
        )

        self._last_request_error_announcement = None

        # Phase 11.11 (Step 3): a structured, deterministic record of
        # what happened during the MOST RECENT listen() call - exposed
        # as a plain instance attribute (never a raw-audio persistence
        # mechanism - only scalars/strings/booleans, and only the most
        # recent call's data, overwritten every time), so tests can
        # directly assert "did Google recognize it", "was Whisper
        # invoked", "was a Whisper result rejected for low confidence",
        # etc., without parsing console output. listen()'s own return
        # value/contract (a plain string) is completely unchanged -
        # this is purely additive. See _reset_diagnostics()/individual
        # update sites throughout this class.
        self.last_diagnostics = _new_diagnostics()

    def _reset_diagnostics(self):
        self.last_diagnostics = _new_diagnostics()

    def calibrate_microphone(self):
        """One-time ambient noise calibration, meant to be called once at
        startup. Sets a better starting energy_threshold based on actual
        room noise; dynamic_energy_threshold keeps adapting afterwards.

        Never raises - if no microphone is available, this is skipped
        and JARVIS continues starting up.
        """

        try:

            with sr.Microphone() as source:

                print("Calibrating microphone for ambient noise...")

                if config.DEBUG:
                    print(f"[DEBUG] microphone: {_describe_microphone(source)}")

                self.recognizer.adjust_for_ambient_noise(
                    source,
                    duration=config.AMBIENT_NOISE_DURATION
                )

                if config.DEBUG:
                    print(
                        "[DEBUG] calibrated energy_threshold="
                        f"{self.recognizer.energy_threshold:.2f} "
                        f"(duration={config.AMBIENT_NOISE_DURATION}s)"
                    )

        except Exception as error:

            print(f"Microphone calibration skipped: {error}")

    def listen(self, timeout=5, phrase_limit=8):
        """Listen once and return recognized text, or "" if nothing could
        be captured or understood. Never raises."""

        self._reset_diagnostics()

        audio = self._capture_audio(timeout, phrase_limit)

        if audio is None:
            return ""

        self.last_diagnostics["audio_captured"] = True

        result = self._recognize(audio)

        self.last_diagnostics["final_result"] = result

        return result

    def listen_with_retry(self, timeout=5, phrase_limit=8, retries=None):
        """Like listen(), but if nothing is understood, asks the user to
        repeat and tries again, up to `retries` extra times (default:
        config.COMMAND_RECOGNITION_RETRIES)."""

        if retries is None:
            retries = config.COMMAND_RECOGNITION_RETRIES

        for attempt in range(retries + 1):

            result = self.listen(timeout=timeout, phrase_limit=phrase_limit)

            if result:
                return result

            if attempt < retries:
                self.voice.speak("Sorry, I didn't catch that. Please repeat.")

        return ""

    def _capture_audio(self, timeout, phrase_limit):

        started = time.monotonic()

        try:

            with sr.Microphone() as source:

                print("Listening...")

                audio = self.recognizer.listen(
                    source,
                    timeout=timeout,
                    phrase_time_limit=phrase_limit
                )

            self.last_diagnostics["capture_wall_time"] = time.monotonic() - started
            self.last_diagnostics["capture_audio_duration"] = _audio_duration_seconds(audio)

            if config.DEBUG:
                print(
                    f"[DEBUG] capture wall_time={self.last_diagnostics['capture_wall_time']:.2f}s "
                    f"audio_duration={self.last_diagnostics['capture_audio_duration']:.2f}s"
                )

            return audio

        except sr.WaitTimeoutError:

            self.last_diagnostics["capture_wall_time"] = time.monotonic() - started

            if config.DEBUG:
                print(
                    "[DEBUG] capture wall_time="
                    f"{self.last_diagnostics['capture_wall_time']:.2f}s -> WaitTimeoutError "
                    "(no speech-like audio crossed the energy threshold)"
                )

            return None

        except Exception as error:

            print(f"Microphone error: {error}")
            return None

    def _recognize(self, audio):

        print("Processing...")

        self.last_diagnostics["google_attempted"] = True

        for attempt in range(config.SPEECH_API_RETRIES + 1):

            try:

                command = self.online_backend.recognize(
                    self.recognizer, audio
                )

                print(f"You: {command}")

                self.last_diagnostics["google_result"] = command
                self.last_diagnostics["final_source"] = "google"

                return command

            except stt_backend.SpeechUnintelligible:

                print("Could not understand the speech.")

                self.last_diagnostics["google_error"] = "unintelligible"

                # Phase 11.4: if enabled, try Urdu on the SAME captured
                # audio before falling back to the offline backend -
                # a single, non-retried attempt (no loop, no re-
                # capture - see _try_urdu_fallback() below). Reachable
                # ONLY from this SpeechUnintelligible branch, never from
                # the RecognitionNetworkError branch below (unmodified
                # by this phase) - a failed network/API call carries no
                # information about the audio's language, so retrying
                # in Urdu there would not be meaningfully different
                # from retrying in English, which config.
                # SPEECH_API_RETRIES already does. See the Phase 11.4
                # architecture audit, section 6.
                if config.ENABLE_URDU_STT_FALLBACK:

                    urdu_result = self._try_urdu_fallback(audio)

                    if urdu_result:
                        return urdu_result

                # The online backend understood there was audio but
                # couldn't transcribe it - still worth trying the
                # offline backend, in case it does better. If it can't
                # either (including "not installed", the current,
                # expected state - see stt_backend.py), this returns
                # "" exactly like before Phase 10.1. Reached whether or
                # not the Urdu attempt above ran, and whether or not it
                # succeeded - Urdu failing is not itself an error, just
                # another "nothing recognized" outcome, same as every
                # other backend/language attempt in this method.
                return self._try_offline_fallback(audio)

            except stt_backend.RecognitionNetworkError as error:

                print(f"Speech recognition error: {error}")

                self.last_diagnostics["google_error"] = "network_error"

                # Transient network/API errors: retry recognition on the
                # SAME captured audio (no need to make the user repeat
                # themselves) before giving up.
                if attempt < config.SPEECH_API_RETRIES:
                    time.sleep(config.SPEECH_API_RETRY_DELAY)
                    continue

                offline_result = self._try_offline_fallback(audio)

                if offline_result:
                    return offline_result

                self._announce_request_error()
                return ""

        return ""

    def _try_urdu_fallback(self, audio):
        """Phase 11.4: attempt Urdu recognition on the SAME captured
        `audio` - never re-captures the microphone, never retries (a
        single attempt, no loop). Only ever called from _recognize()'s
        SpeechUnintelligible branch, when config.ENABLE_URDU_STT_
        FALLBACK is True. Never raises - returns "" on any failure
        (SpeechUnintelligible or RecognitionNetworkError), exactly like
        _try_offline_fallback() below returns "" on any of its own
        failure cases - so the caller always proceeds to the existing
        offline fallback next, regardless of why this attempt didn't
        produce text."""

        self.last_diagnostics["urdu_attempted"] = True

        try:

            command = self.urdu_online_backend.recognize(
                self.recognizer, audio
            )

            print(f"You (Urdu): {command}")

            self.last_diagnostics["urdu_result"] = command
            self.last_diagnostics["final_source"] = "urdu"

            return command

        except stt_backend.SpeechUnintelligible:
            print("Could not understand the speech in Urdu either.")
            return ""

        except stt_backend.RecognitionNetworkError as error:
            print(f"Urdu speech recognition error: {error}")
            return ""

    def _try_offline_fallback(self, audio):
        """Attempt the offline backend after the online backend failed
        to produce text. Never raises - returns "" if the offline
        backend is disabled, unavailable, itself fails, or also can't
        understand the audio, exactly like every other "nothing
        recognized" case. Callers of listen() can't tell the
        difference between any of these cases, by design (same as
        before Phase 10.1)."""

        if not config.OFFLINE_STT_ENABLED:
            return ""

        if not self.offline_backend.is_available():
            print(
                f"Offline backend '{self.offline_backend.name}' "
                "is not available."
            )
            return ""

        self.last_diagnostics["whisper_invoked"] = True

        try:

            command = self.offline_backend.recognize(
                self.recognizer, audio
            )

            print(f"You (offline): {command}")

            self.last_diagnostics["whisper_result"] = command
            self.last_diagnostics["whisper_confidence"] = self.offline_backend.last_confidence
            self.last_diagnostics["final_source"] = "offline_whisper"

            return command

        except stt_backend.SpeechUnintelligible:

            print("Offline backend could not understand the speech either.")

            avg_no_speech_prob, avg_logprob = self.offline_backend.last_confidence
            self.last_diagnostics["whisper_confidence"] = (
                avg_no_speech_prob, avg_logprob
            )
            self.last_diagnostics["whisper_rejected_low_confidence"] = (
                config.ENABLE_WHISPER_CONFIDENCE_GATE
                and stt_backend._confidence_signal_is_low(
                    avg_no_speech_prob, avg_logprob
                )
            )

            return ""

        except stt_backend.BackendUnavailable as error:
            print(f"Offline backend unavailable: {error}")
            return ""

        except stt_backend.BackendFailure as error:
            print(f"Offline backend failed: {error}")
            return ""

        except stt_backend.RecognitionNetworkError as error:
            # Not expected from an offline backend, but handled the
            # same defensive, never-raise way as every other backend
            # failure above.
            print(f"Offline backend error: {error}")
            return ""

    def _announce_request_error(self):
        """Speak the connectivity warning, but not more than once per
        config.REQUEST_ERROR_ANNOUNCE_COOLDOWN seconds, so a prolonged
        outage doesn't repeat the announcement on every listen cycle."""

        now = time.monotonic()

        if (
            self._last_request_error_announcement is not None
            and now - self._last_request_error_announcement
            < config.REQUEST_ERROR_ANNOUNCE_COOLDOWN
        ):
            return

        self._last_request_error_announcement = now

        self.voice.speak(
            "I am having trouble connecting to speech recognition."
        )
