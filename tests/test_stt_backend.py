from unittest.mock import Mock, patch

import speech_recognition as sr

import stt_backend


# ---------------------------------------------------------------------
# GoogleOnlineBackend
# ---------------------------------------------------------------------

def test_google_online_backend_is_always_available():
    backend = stt_backend.GoogleOnlineBackend()
    assert backend.is_available() is True


def test_google_online_backend_recognize_success():
    backend = stt_backend.GoogleOnlineBackend()
    recognizer = Mock()
    recognizer.recognize_google.return_value = "Open Chrome"

    result = backend.recognize(recognizer, audio=object())

    assert result == "open chrome"


def test_google_online_backend_unknown_value_raises_speech_unintelligible():
    backend = stt_backend.GoogleOnlineBackend()
    recognizer = Mock()
    recognizer.recognize_google.side_effect = sr.UnknownValueError()

    try:
        backend.recognize(recognizer, audio=object())
        assert False, "expected SpeechUnintelligible"
    except stt_backend.SpeechUnintelligible:
        pass


def test_google_online_backend_request_error_raises_network_error():
    backend = stt_backend.GoogleOnlineBackend()
    recognizer = Mock()
    recognizer.recognize_google.side_effect = sr.RequestError("boom")

    try:
        backend.recognize(recognizer, audio=object())
        assert False, "expected RecognitionNetworkError"
    except stt_backend.RecognitionNetworkError:
        pass


# ---------------------------------------------------------------------
# Phase 11.4: GoogleOnlineBackend(language=...) - optional language
# override, backward-compatible zero-argument construction.
# ---------------------------------------------------------------------

def test_google_online_backend_default_construction_uses_config_recognition_language():
    """Zero-argument construction (every pre-11.4 call site) must keep
    reading config.RECOGNITION_LANGUAGE FRESH on every recognize() call
    - not a value cached at construction time - exactly like before
    this parameter existed."""

    backend = stt_backend.GoogleOnlineBackend()
    recognizer = Mock()
    recognizer.recognize_google.return_value = "hello"
    fake_audio = object()

    with patch("stt_backend.config.RECOGNITION_LANGUAGE", "en-US"):
        backend.recognize(recognizer, audio=fake_audio)

    recognizer.recognize_google.assert_called_once_with(
        fake_audio, language="en-US"
    )

    # And a DIFFERENT config value takes effect on the very next call -
    # proving the language is resolved at call time, not cached.
    with patch("stt_backend.config.RECOGNITION_LANGUAGE", "fr-FR"):
        backend.recognize(recognizer, audio=fake_audio)

    assert recognizer.recognize_google.call_args.kwargs["language"] == "fr-FR"


def test_google_online_backend_explicit_language_overrides_config():
    backend = stt_backend.GoogleOnlineBackend(language="ur-PK")
    recognizer = Mock()
    recognizer.recognize_google.return_value = "some text"
    fake_audio = object()

    backend.recognize(recognizer, audio=fake_audio)

    recognizer.recognize_google.assert_called_once_with(
        fake_audio, language="ur-PK"
    )


def test_google_online_backend_explicit_language_ignores_config_changes():
    """A backend constructed with an explicit language must never fall
    back to config.RECOGNITION_LANGUAGE, even if that config value
    changes after construction."""

    backend = stt_backend.GoogleOnlineBackend(language="ur-PK")
    recognizer = Mock()
    recognizer.recognize_google.return_value = "some text"

    with patch("stt_backend.config.RECOGNITION_LANGUAGE", "fr-FR"):
        backend.recognize(recognizer, audio=object())

    assert recognizer.recognize_google.call_args.kwargs["language"] == "ur-PK"


def test_google_online_backend_default_language_attribute_is_none():
    """Structural check: the stored `language` attribute is None for a
    zero-argument construction - the resolution to config.
    RECOGNITION_LANGUAGE happens inside recognize(), not __init__."""

    backend = stt_backend.GoogleOnlineBackend()
    assert backend.language is None


def test_google_online_backend_stores_explicit_language_attribute():
    backend = stt_backend.GoogleOnlineBackend(language="ur-PK")
    assert backend.language == "ur-PK"


def test_google_online_backend_still_maps_exceptions_with_explicit_language():
    """The UnknownValueError/RequestError -> SpeechUnintelligible/
    RecognitionNetworkError mapping is unaffected by the language
    parameter - proven for a non-default-language instance too."""

    backend = stt_backend.GoogleOnlineBackend(language="ur-PK")
    recognizer = Mock()

    recognizer.recognize_google.side_effect = sr.UnknownValueError()
    try:
        backend.recognize(recognizer, audio=object())
        assert False, "expected SpeechUnintelligible"
    except stt_backend.SpeechUnintelligible:
        pass

    recognizer.recognize_google.side_effect = sr.RequestError("boom")
    try:
        backend.recognize(recognizer, audio=object())
        assert False, "expected RecognitionNetworkError"
    except stt_backend.RecognitionNetworkError:
        pass


# ---------------------------------------------------------------------
# OfflineWhisperBackend availability
#
# Phase 10.1 originally shipped with faster_whisper NOT installed, so
# is_available() genuinely returned False with zero mocking - a real,
# unmocked, environment-driven check. The Phase 10.1 install/validation
# step then installed faster_whisper into this project's .venv (an
# explicit, approved action - see the Phase 10.1 faster-whisper
# validation report), which deliberately changed that real-environment
# result to True. test_offline_backend_reports_unavailable_when_
# dependency_missing below is updated accordingly, in place of being
# deleted, to keep asserting the (now-true) real, unmocked fact.
#
# test_offline_backend_recognize_raises_backend_unavailable_when_not_
# installed no longer reflects reality if left unmocked (calling
# recognize() would now reach the REAL recognize_faster_whisper() path
# via the Mock recognizer, which is unsafe/undefined) - so it now
# explicitly mocks is_available() to False, which tests the exact same
# "unavailable" behavior without depending on what happens to be
# installed in this environment. This is an intentional test update
# reflecting a deliberately changed environment, not a weakened test.
# ---------------------------------------------------------------------

def test_offline_backend_reports_available_now_that_dependency_is_installed():
    backend = stt_backend.OfflineWhisperBackend()
    assert backend.is_available() is True


def test_offline_backend_recognize_raises_backend_unavailable_when_not_installed():
    backend = stt_backend.OfflineWhisperBackend()
    recognizer = Mock()

    with patch.object(backend, "is_available", return_value=False):
        try:
            backend.recognize(recognizer, audio=object())
            assert False, "expected BackendUnavailable"
        except stt_backend.BackendUnavailable:
            pass

    recognizer.recognize_faster_whisper.assert_not_called()


def test_offline_backend_recognize_success_when_available():
    backend = stt_backend.OfflineWhisperBackend()
    recognizer = Mock()
    recognizer.recognize_faster_whisper.return_value = {
        "text": "Set Volume To 40", "segments": [], "language": "en",
    }

    with patch.object(backend, "is_available", return_value=True):
        result = backend.recognize(recognizer, audio=object())

    assert result == "set volume to 40"


def test_offline_backend_recognize_passes_configured_model_and_device():
    import config

    backend = stt_backend.OfflineWhisperBackend()
    recognizer = Mock()
    recognizer.recognize_faster_whisper.return_value = {
        "text": "open chrome", "segments": [], "language": "en",
    }

    with patch.object(backend, "is_available", return_value=True):
        backend.recognize(recognizer, audio=object())

    _, kwargs = recognizer.recognize_faster_whisper.call_args
    assert kwargs["model"] == config.OFFLINE_STT_MODEL
    assert kwargs["show_dict"] is True
    assert kwargs["init_options"]["device"] == config.OFFLINE_STT_DEVICE
    assert kwargs["init_options"]["compute_type"] == config.OFFLINE_STT_COMPUTE_TYPE


def test_offline_backend_recognize_unknown_value_raises_speech_unintelligible():
    backend = stt_backend.OfflineWhisperBackend()
    recognizer = Mock()
    recognizer.recognize_faster_whisper.side_effect = sr.UnknownValueError()

    with patch.object(backend, "is_available", return_value=True):
        try:
            backend.recognize(recognizer, audio=object())
            assert False, "expected SpeechUnintelligible"
        except stt_backend.SpeechUnintelligible:
            pass


def test_offline_backend_recognize_empty_result_raises_speech_unintelligible():
    backend = stt_backend.OfflineWhisperBackend()
    recognizer = Mock()
    recognizer.recognize_faster_whisper.return_value = {
        "text": "", "segments": [], "language": "en",
    }

    with patch.object(backend, "is_available", return_value=True):
        try:
            backend.recognize(recognizer, audio=object())
            assert False, "expected SpeechUnintelligible"
        except stt_backend.SpeechUnintelligible:
            pass


def test_offline_backend_recognize_unexpected_error_raises_backend_failure():
    backend = stt_backend.OfflineWhisperBackend()
    recognizer = Mock()
    recognizer.recognize_faster_whisper.side_effect = RuntimeError("model load failed")

    with patch.object(backend, "is_available", return_value=True):
        try:
            backend.recognize(recognizer, audio=object())
            assert False, "expected BackendFailure"
        except stt_backend.BackendFailure:
            pass


def test_offline_backend_recognize_import_error_raises_backend_unavailable():
    backend = stt_backend.OfflineWhisperBackend()
    recognizer = Mock()
    recognizer.recognize_faster_whisper.side_effect = ImportError("no module")

    with patch.object(backend, "is_available", return_value=True):
        try:
            backend.recognize(recognizer, audio=object())
            assert False, "expected BackendUnavailable"
        except stt_backend.BackendUnavailable:
            pass


# =======================================================================
# PHASE 11.11 (Step 3/5/6): Whisper confidence signal - genuine, model-
# provided quality data (avg_logprob/no_speech_prob per faster_whisper.
# transcribe.Segment), reached via show_dict=True. See config.
# ENABLE_WHISPER_CONFIDENCE_GATE's own extensive comment for why the
# two thresholds used here are PROVISIONAL, not live-tuned.
# =======================================================================

def _fake_segment(avg_logprob=None, no_speech_prob=None):
    """A minimal stand-in for faster_whisper.transcribe.Segment -
    only the two fields this project's confidence signal reads."""
    return type(
        "FakeSegment", (), {"avg_logprob": avg_logprob, "no_speech_prob": no_speech_prob}
    )()


# ---- _whisper_confidence_signal() - pure ----

def test_confidence_signal_empty_segments_returns_none_none():
    assert stt_backend._whisper_confidence_signal([]) == (None, None)


def test_confidence_signal_averages_across_multiple_segments():
    segments = [
        _fake_segment(avg_logprob=-0.2, no_speech_prob=0.1),
        _fake_segment(avg_logprob=-0.4, no_speech_prob=0.3),
    ]
    avg_no_speech, avg_logprob = stt_backend._whisper_confidence_signal(segments)
    assert avg_no_speech == 0.2
    assert abs(avg_logprob - (-0.3)) < 1e-9


def test_confidence_signal_ignores_segments_missing_fields():
    segments = [_fake_segment(avg_logprob=None, no_speech_prob=None)]
    assert stt_backend._whisper_confidence_signal(segments) == (None, None)


def test_confidence_signal_never_raises_on_malformed_segments():
    assert stt_backend._whisper_confidence_signal(None) == (None, None)
    assert stt_backend._whisper_confidence_signal([object()]) == (None, None)


# ---- _confidence_signal_is_low() / _whisper_result_is_low_confidence()
# - pure ----

def test_confidence_signal_is_low_none_none_is_never_low():
    assert stt_backend._confidence_signal_is_low(None, None) is False


def test_confidence_signal_is_low_high_no_speech_prob():
    import config

    assert stt_backend._confidence_signal_is_low(
        config.WHISPER_MAX_NO_SPEECH_PROB, -0.1
    ) is True
    assert stt_backend._confidence_signal_is_low(
        config.WHISPER_MAX_NO_SPEECH_PROB - 0.3, -0.1
    ) is False


def test_confidence_signal_is_low_poor_avg_logprob():
    import config

    assert stt_backend._confidence_signal_is_low(
        0.1, config.WHISPER_MIN_AVG_LOGPROB
    ) is True
    assert stt_backend._confidence_signal_is_low(
        0.1, config.WHISPER_MIN_AVG_LOGPROB + 0.5
    ) is False


def test_whisper_result_is_low_confidence_uses_segment_list():
    low_confidence_segments = [_fake_segment(avg_logprob=-5.0, no_speech_prob=0.9)]
    high_confidence_segments = [_fake_segment(avg_logprob=-0.1, no_speech_prob=0.05)]

    assert stt_backend._whisper_result_is_low_confidence(low_confidence_segments) is True
    assert stt_backend._whisper_result_is_low_confidence(high_confidence_segments) is False
    assert stt_backend._whisper_result_is_low_confidence([]) is False


# ---- OfflineWhisperBackend.recognize() - show_dict=True wiring ----

def test_offline_backend_recognize_uses_show_dict_true():
    backend = stt_backend.OfflineWhisperBackend()
    recognizer = Mock()
    recognizer.recognize_faster_whisper.return_value = {
        "text": "open chrome", "segments": [], "language": "en",
    }

    with patch.object(backend, "is_available", return_value=True):
        backend.recognize(recognizer, audio=object())

    assert recognizer.recognize_faster_whisper.call_args.kwargs["show_dict"] is True


def test_offline_backend_records_last_confidence_on_success():
    backend = stt_backend.OfflineWhisperBackend()
    recognizer = Mock()
    recognizer.recognize_faster_whisper.return_value = {
        "text": "open chrome",
        "segments": [_fake_segment(avg_logprob=-0.2, no_speech_prob=0.1)],
        "language": "en",
    }

    with patch.object(backend, "is_available", return_value=True):
        backend.recognize(recognizer, audio=object())

    assert backend.last_confidence == (0.1, -0.2)


def test_offline_backend_last_confidence_defaults_none_none():
    backend = stt_backend.OfflineWhisperBackend()
    assert backend.last_confidence == (None, None)


# ---- Gate OFF (default): accepts regardless of confidence - byte-for-
# byte unchanged from before Phase 11.11 ----

def test_confidence_gate_off_accepts_low_confidence_text_by_default():
    import config

    backend = stt_backend.OfflineWhisperBackend()
    recognizer = Mock()
    recognizer.recognize_faster_whisper.return_value = {
        "text": "something hallucinated",
        "segments": [_fake_segment(avg_logprob=-5.0, no_speech_prob=0.95)],
        "language": "en",
    }

    assert config.ENABLE_WHISPER_CONFIDENCE_GATE is False

    with patch.object(backend, "is_available", return_value=True):
        result = backend.recognize(recognizer, audio=object())

    assert result == "something hallucinated"


# ---- Gate ON: rejects low-confidence / obvious-hallucination text ----

def test_confidence_gate_on_rejects_low_confidence_hallucination():
    import config

    backend = stt_backend.OfflineWhisperBackend()
    recognizer = Mock()
    recognizer.recognize_faster_whisper.return_value = {
        "text": "täällä on yleensä",  # the exact class of hallucinated
                                       # text observed live in Phase
                                       # 11.10 (Finnish, from noise)
        "segments": [_fake_segment(avg_logprob=-5.0, no_speech_prob=0.95)],
        "language": "fi",
    }

    with patch.object(config, "ENABLE_WHISPER_CONFIDENCE_GATE", True), \
         patch.object(backend, "is_available", return_value=True):
        try:
            backend.recognize(recognizer, audio=object())
            assert False, "expected SpeechUnintelligible"
        except stt_backend.SpeechUnintelligible:
            pass


def test_confidence_gate_on_still_accepts_high_confidence_text():
    import config

    backend = stt_backend.OfflineWhisperBackend()
    recognizer = Mock()
    recognizer.recognize_faster_whisper.return_value = {
        "text": "open chrome",
        "segments": [_fake_segment(avg_logprob=-0.15, no_speech_prob=0.05)],
        "language": "en",
    }

    with patch.object(config, "ENABLE_WHISPER_CONFIDENCE_GATE", True), \
         patch.object(backend, "is_available", return_value=True):
        result = backend.recognize(recognizer, audio=object())

    assert result == "open chrome"


def test_confidence_gate_on_with_no_segment_data_still_accepts():
    """Fail-permissive: text with NO usable confidence signal at all
    (e.g. a faster-whisper response shape this project didn't
    anticipate) must never be rejected purely for lacking that signal -
    only an ACTUAL low-confidence signal rejects."""

    import config

    backend = stt_backend.OfflineWhisperBackend()
    recognizer = Mock()
    recognizer.recognize_faster_whisper.return_value = {
        "text": "open chrome", "segments": [], "language": "en",
    }

    with patch.object(config, "ENABLE_WHISPER_CONFIDENCE_GATE", True), \
         patch.object(backend, "is_available", return_value=True):
        result = backend.recognize(recognizer, audio=object())

    assert result == "open chrome"


# ---- Unicode transcription safety at the backend level ----

def test_google_backend_returns_unicode_text_without_raising():
    backend = stt_backend.GoogleOnlineBackend()
    recognizer = Mock()
    recognizer.recognize_google.return_value = "کمپیوٹر بند کرو"

    result = backend.recognize(recognizer, audio=object())

    assert result == "کمپیوٹر بند کرو"


def test_offline_backend_returns_unicode_text_without_raising():
    backend = stt_backend.OfflineWhisperBackend()
    recognizer = Mock()
    recognizer.recognize_faster_whisper.return_value = {
        "text": "پخنے ہوچے یہیں", "segments": [], "language": "hi",
    }

    with patch.object(backend, "is_available", return_value=True):
        result = backend.recognize(recognizer, audio=object())

    assert result == "پخنے ہوچے یہیں"
