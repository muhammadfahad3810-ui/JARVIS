"""Speech-to-text backend abstraction (Phase 10.1).

Speech (speech.py) is written against this interface, not against any
one recognition engine, so a new backend can be added later without
changing Speech's public contract (Speech.listen() still returns a
plain string, or "" - never raises). Two backends exist as of Phase
10.1:

- GoogleOnlineBackend: the same online recognize_google() call Speech
  has used since Phase 1 - unchanged behavior, still the primary
  backend.
- OfflineWhisperBackend: a fallback for when the online backend can't
  produce a result. It calls speech_recognition's own built-in
  recognize_faster_whisper() adapter (bundled with
  SpeechRecognition==3.17.0, already installed), which lazily imports
  the separate `faster_whisper` package only when actually called.

  As of Phase 10.1, `faster_whisper` is NOT installed in this project
  (see the Phase 10.1 dependency decision - faster-whisper was chosen
  but installation was deferred pending approval). is_available()
  correctly reports False until it is installed; every caller treats
  "offline backend unavailable" as a normal, expected, non-error case.
"""

import config
import speech_recognition as sr


class SpeechUnintelligible(Exception):
    """Audio was captured, but this backend could not make out any
    words in it (as opposed to a connectivity or backend problem)."""


class RecognitionNetworkError(Exception):
    """This backend could not reach (or was rejected by) whatever
    recognition service it depends on - e.g. no internet connection,
    DNS failure, API outage."""


class BackendUnavailable(Exception):
    """This backend cannot run at all right now - its optional
    dependency is not installed, or it isn't otherwise configured."""


class BackendFailure(Exception):
    """This backend attempted to recognize speech but hit an
    unexpected internal error, unrelated to network connectivity or
    to the audio being unintelligible."""


class STTBackend:
    """Base interface every speech-to-text backend implements."""

    name = "base"

    def is_available(self):
        """Return True if this backend can be used right now."""
        raise NotImplementedError

    def recognize(self, recognizer, audio):
        """Return recognized text (lowercased, stripped).

        Only ever raises SpeechUnintelligible, RecognitionNetworkError,
        BackendUnavailable, or BackendFailure - callers only need to
        handle these four, never a raw library exception.
        """
        raise NotImplementedError


class GoogleOnlineBackend(STTBackend):
    """The original Phase 1-9 backend: speech_recognition's free
    Google Web Speech API client. Requires internet connectivity.

    Phase 11.4: accepts an optional `language` override so a second
    instance can be constructed for a different language (see speech.
    Speech.__init__'s urdu_online_backend) without a new backend class.
    `language=None` (the default, and every pre-11.4 zero-argument call
    site) preserves the EXACT existing behavior byte-for-byte: recognize
    () reads config.RECOGNITION_LANGUAGE fresh on every call, not a
    value cached at construction time - so a test or caller that
    changes config.RECOGNITION_LANGUAGE after constructing a default
    GoogleOnlineBackend() still sees that change take effect, exactly
    as before this parameter existed.
    """

    name = "google_online"

    def __init__(self, language=None):
        self.language = language

    def is_available(self):
        # Always considered configured/available - whether the
        # network is actually reachable is only known once recognize()
        # is tried, same as before Phase 10.1.
        return True

    def recognize(self, recognizer, audio):

        try:

            text = recognizer.recognize_google(
                audio,
                language=self.language or config.RECOGNITION_LANGUAGE
            )

        except sr.UnknownValueError:
            raise SpeechUnintelligible()

        except sr.RequestError as error:
            raise RecognitionNetworkError(str(error))

        return text.lower().strip()


def _whisper_confidence_signal(segments):
    """Phase 11.11 (Step 3/5). Pure - never raises, never touches audio.
    `segments` is the list of faster_whisper.transcribe.Segment objects
    returned by recognize_faster_whisper(..., show_dict=True)["segments"]
    - each one already carries avg_logprob (average log-probability of
    its decoded tokens - higher/less-negative means more confident) and
    no_speech_prob (the model's own probability that the segment is NOT
    speech at all) as genuine, model-provided quality signals, not a
    guessed heuristic derived from this project's own audio-energy
    data.

    Returns (avg_no_speech_prob, avg_logprob), each None if no segments
    (or no segments with that particular field) were available - e.g.
    a completely empty transcription, which the caller already treats
    as SpeechUnintelligible via the existing empty-text check,
    independent of this confidence signal.
    """

    if not segments:
        return None, None

    no_speech_probs = [
        getattr(segment, "no_speech_prob", None) for segment in segments
    ]
    avg_logprobs = [
        getattr(segment, "avg_logprob", None) for segment in segments
    ]

    no_speech_probs = [p for p in no_speech_probs if p is not None]
    avg_logprobs = [p for p in avg_logprobs if p is not None]

    avg_no_speech_prob = (
        sum(no_speech_probs) / len(no_speech_probs) if no_speech_probs else None
    )
    avg_logprob = (
        sum(avg_logprobs) / len(avg_logprobs) if avg_logprobs else None
    )

    return avg_no_speech_prob, avg_logprob


def _confidence_signal_is_low(avg_no_speech_prob, avg_logprob):
    """Phase 11.11 (Step 5/6). Pure. True if either half of an already-
    computed (avg_no_speech_prob, avg_logprob) signal (see
    _whisper_confidence_signal() above) crosses its PROVISIONAL
    threshold in config.py (see config.ENABLE_WHISPER_CONFIDENCE_GATE's
    own extensive comment for why they're provisional and not yet
    live-tuned). None for either value is NEVER treated as low-
    confidence - fail-permissive on purpose, since the existing empty-
    text check already guards the "nothing at all" case; this
    function's only job is filtering PLAUSIBLE-LOOKING but actually-
    unreliable hallucinated text. Split out from _whisper_result_is_
    low_confidence() below so callers that already have the signal
    (e.g. speech.Speech's own diagnostics, reading OfflineWhisperBackend
    .last_confidence) don't need the original segment list to ask the
    same question."""

    if (
        avg_no_speech_prob is not None
        and avg_no_speech_prob >= config.WHISPER_MAX_NO_SPEECH_PROB
    ):
        return True

    if (
        avg_logprob is not None
        and avg_logprob <= config.WHISPER_MIN_AVG_LOGPROB
    ):
        return True

    return False


def _whisper_result_is_low_confidence(segments):
    """Phase 11.11 (Step 5/6). Pure. See _confidence_signal_is_low()
    above - this is the segment-list-taking entry point actually used
    by OfflineWhisperBackend.recognize()."""

    avg_no_speech_prob, avg_logprob = _whisper_confidence_signal(segments)
    return _confidence_signal_is_low(avg_no_speech_prob, avg_logprob)


class OfflineWhisperBackend(STTBackend):
    """Offline fallback using speech_recognition's built-in
    recognize_faster_whisper() adapter. Requires the separate
    `faster_whisper` package, which is NOT installed as of Phase
    10.1 (see the Phase 10.1 dependency decision) - until it is,
    is_available() reports False and this backend is a documented,
    tested, inert no-op."""

    name = "offline_whisper"

    def __init__(self):
        # Phase 11.11 (Step 3): the confidence signal (avg_no_speech_
        # prob, avg_logprob) from the MOST RECENT recognize() call -
        # (None, None) before any call, or if it couldn't be computed.
        # Exposed as a plain instance attribute (same pattern as
        # speech.Speech.last_diagnostics) purely for diagnostics/
        # testing - reading it has no effect on recognize()'s own
        # return value or exceptions, and it is never persisted to
        # disk or logged with raw audio.
        self.last_confidence = (None, None)

    def is_available(self):

        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return False

        return True

    def recognize(self, recognizer, audio):

        if not self.is_available():
            raise BackendUnavailable(
                "faster_whisper is not installed"
            )

        try:

            # Phase 11.11 (Step 3/5): show_dict=True costs nothing
            # extra - the underlying model.transcribe() call happens
            # either way (see speech_recognition.recognizers.
            # whisper_local.base.WhisperCompatibleRecognizer.recognize()
            # - show_dict only controls whether the wrapper returns the
            # full dict or just result["text"]) - so segment-level
            # confidence data is now always available for diagnostics,
            # independent of whether the gate itself is enabled.
            result = recognizer.recognize_faster_whisper(
                audio,
                model=config.OFFLINE_STT_MODEL,
                show_dict=True,
                init_options={
                    "device": config.OFFLINE_STT_DEVICE,
                    "compute_type": config.OFFLINE_STT_COMPUTE_TYPE,
                },
            )

        except sr.UnknownValueError:
            self.last_confidence = (None, None)
            raise SpeechUnintelligible()

        except ImportError as error:
            raise BackendUnavailable(str(error))

        except Exception as error:
            raise BackendFailure(str(error))

        # show_dict=True always yields a dict shape (see speech_
        # recognition.recognizers.whisper_local.base.
        # WhisperCompatibleRecognizer.recognize()) - {"text": str,
        # "segments": [...], "language": str}.
        text = (result.get("text") or "").strip()
        segments = result.get("segments") or []

        self.last_confidence = _whisper_confidence_signal(segments)

        if not text:
            raise SpeechUnintelligible()

        # Phase 11.11 (Step 5/6): default OFF - see config.
        # ENABLE_WHISPER_CONFIDENCE_GATE's own extensive comment for
        # why the two thresholds this checks are provisional. With the
        # flag off (the default), this is dead code and behavior is
        # byte-for-byte unchanged from before this phase.
        if config.ENABLE_WHISPER_CONFIDENCE_GATE and _whisper_result_is_low_confidence(segments):
            raise SpeechUnintelligible()

        return text.lower().strip()
