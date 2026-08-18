from unittest.mock import patch

import speech_recognition as sr

import config
import speech as speech_module
import stt_backend


class FakeVoice:
    def __init__(self):
        self.spoken = []

    def speak(self, text):
        self.spoken.append(text)


def make_speech():
    voice = FakeVoice()
    return speech_module.Speech(voice), voice


# ---------------------------------------------------------------------
# listen() - success / error handling
# ---------------------------------------------------------------------

def test_listen_successful_recognition():
    s, voice = make_speech()
    fake_audio = object()

    with patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio), \
         patch.object(
             s.recognizer, "recognize_google", return_value="Open Chrome"
         ) as mock_recognize:
        result = s.listen()

    assert result == "open chrome"
    mock_recognize.assert_called_once()


def test_listen_unknown_value_error_returns_empty_string():
    s, voice = make_speech()
    fake_audio = object()

    with patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio), \
         patch.object(
             s.recognizer, "recognize_google",
             side_effect=sr.UnknownValueError()
         ):
        result = s.listen()

    assert result == ""
    assert voice.spoken == []


def test_listen_wait_timeout_returns_empty_string():
    s, voice = make_speech()

    with patch("speech.sr.Microphone"), \
         patch.object(
             s.recognizer, "listen", side_effect=sr.WaitTimeoutError()
         ):
        result = s.listen()

    assert result == ""


def test_listen_microphone_init_error_does_not_crash():
    s, voice = make_speech()

    with patch(
        "speech.sr.Microphone",
        side_effect=OSError("no default input device"),
    ):
        result = s.listen()

    assert result == ""


# ---------------------------------------------------------------------
# RequestError: same-audio retry + throttled announcement
# ---------------------------------------------------------------------

def test_request_error_retries_same_audio_then_announces():
    s, voice = make_speech()
    fake_audio = object()

    with patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio), \
         patch.object(
             s.recognizer, "recognize_google",
             side_effect=sr.RequestError("boom")
         ) as mock_recognize, \
         patch("speech.time.sleep"):
        result = s.listen()

    assert result == ""
    assert mock_recognize.call_count == 1 + config.SPEECH_API_RETRIES
    assert "trouble connecting" in voice.spoken[-1]


def test_request_error_recovers_on_retry_without_re_listening():
    s, voice = make_speech()
    fake_audio = object()

    with patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio) as mock_listen, \
         patch.object(
             s.recognizer, "recognize_google",
             side_effect=[sr.RequestError("boom"), "open chrome"],
         ), \
         patch("speech.time.sleep"):
        result = s.listen()

    assert result == "open chrome"
    assert voice.spoken == []
    mock_listen.assert_called_once()


def test_request_error_announcement_is_throttled():
    s, voice = make_speech()
    fake_audio = object()

    with patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio), \
         patch.object(
             s.recognizer, "recognize_google",
             side_effect=sr.RequestError("boom")
         ), \
         patch("speech.time.sleep"):
        s.listen()
        s.listen()

    assert voice.spoken.count(
        "I am having trouble connecting to speech recognition."
    ) == 1


# ---------------------------------------------------------------------
# Ambient noise calibration
# ---------------------------------------------------------------------

def test_calibrate_microphone_adjusts_ambient_noise():
    s, voice = make_speech()

    with patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "adjust_for_ambient_noise") as mock_adjust:
        s.calibrate_microphone()

    mock_adjust.assert_called_once()


def test_calibrate_microphone_does_not_raise_without_microphone():
    s, voice = make_speech()

    with patch("speech.sr.Microphone", side_effect=OSError("no mic")):
        s.calibrate_microphone()


# ---------------------------------------------------------------------
# listen_with_retry() - re-listens (asks user to repeat) on empty result
# ---------------------------------------------------------------------

def test_listen_with_retry_returns_first_successful_result():
    s, voice = make_speech()

    with patch.object(s, "listen", side_effect=["", "open chrome"]):
        result = s.listen_with_retry(retries=1)

    assert result == "open chrome"
    assert "Sorry, I didn't catch that. Please repeat." in voice.spoken


def test_listen_with_retry_gives_up_after_max_retries():
    s, voice = make_speech()

    with patch.object(s, "listen", return_value=""):
        result = s.listen_with_retry(retries=1)

    assert result == ""
    assert voice.spoken.count(
        "Sorry, I didn't catch that. Please repeat."
    ) == 1


def test_listen_with_retry_succeeds_immediately_without_prompting():
    s, voice = make_speech()

    with patch.object(s, "listen", return_value="open chrome"):
        result = s.listen_with_retry(retries=1)

    assert result == "open chrome"
    assert voice.spoken == []


# ---------------------------------------------------------------------
# Phase 10.1: offline STT fallback
# ---------------------------------------------------------------------

def test_offline_fallback_succeeds_after_online_network_failure():
    s, voice = make_speech()
    fake_audio = object()

    with patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio), \
         patch.object(
             s.recognizer, "recognize_google",
             side_effect=sr.RequestError("boom")
         ), \
         patch.object(s.offline_backend, "is_available", return_value=True), \
         patch.object(
             s.offline_backend, "recognize", return_value="open chrome"
         ) as mock_offline_recognize, \
         patch("speech.time.sleep"):
        result = s.listen()

    assert result == "open chrome"
    mock_offline_recognize.assert_called_once()
    # Fallback succeeded - the "trouble connecting" warning must not
    # be spoken, since the user's command was actually understood.
    assert voice.spoken == []


def test_offline_fallback_succeeds_after_online_unintelligible():
    s, voice = make_speech()
    fake_audio = object()

    with patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio), \
         patch.object(
             s.recognizer, "recognize_google",
             side_effect=sr.UnknownValueError()
         ), \
         patch.object(s.offline_backend, "is_available", return_value=True), \
         patch.object(
             s.offline_backend, "recognize", return_value="set volume to 40"
         ):
        result = s.listen()

    assert result == "set volume to 40"
    assert voice.spoken == []


def test_offline_fallback_failure_still_announces_network_error():
    s, voice = make_speech()
    fake_audio = object()

    with patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio), \
         patch.object(
             s.recognizer, "recognize_google",
             side_effect=sr.RequestError("boom")
         ), \
         patch.object(s.offline_backend, "is_available", return_value=True), \
         patch.object(
             s.offline_backend, "recognize",
             side_effect=stt_backend.BackendFailure("offline boom")
         ), \
         patch("speech.time.sleep"):
        result = s.listen()

    assert result == ""
    assert "trouble connecting" in voice.spoken[-1]


def test_both_backends_fail_returns_empty_without_crash():
    s, voice = make_speech()
    fake_audio = object()

    with patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio), \
         patch.object(
             s.recognizer, "recognize_google",
             side_effect=sr.UnknownValueError()
         ), \
         patch.object(s.offline_backend, "is_available", return_value=True), \
         patch.object(
             s.offline_backend, "recognize",
             side_effect=stt_backend.SpeechUnintelligible()
         ):
        result = s.listen()

    assert result == ""
    # Genuinely unintelligible on both backends is not a connectivity
    # problem - no "trouble connecting" warning should be spoken.
    assert voice.spoken == []


def test_offline_backend_disabled_by_config_is_never_attempted():
    s, voice = make_speech()
    fake_audio = object()

    with patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio), \
         patch.object(
             s.recognizer, "recognize_google",
             side_effect=sr.RequestError("boom")
         ), \
         patch.object(s.offline_backend, "is_available") as mock_available, \
         patch("speech.config.OFFLINE_STT_ENABLED", False), \
         patch("speech.time.sleep"):
        result = s.listen()

    assert result == ""
    mock_available.assert_not_called()
    assert "trouble connecting" in voice.spoken[-1]


def test_offline_backend_unavailable_falls_through_like_before_phase_10_1():
    """faster_whisper is now installed (Phase 10.1 install/validation
    step), so OfflineWhisperBackend.is_available() genuinely returns
    True in this environment - unlike when this test was first
    written. is_available() is explicitly mocked back to False here so
    this test keeps exercising the "offline backend unavailable"
    fallback path deterministically, without depending on what happens
    to be installed, and without ever reaching the real
    recognize_faster_whisper() call (which would be unsafe to trigger
    unmocked in a unit test - see the Phase 10.1 faster-whisper
    validation report). Behavior must be identical to before Phase
    10.1: announce once, return ""."""
    s, voice = make_speech()
    fake_audio = object()

    with patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio), \
         patch.object(
             s.recognizer, "recognize_google",
             side_effect=sr.RequestError("boom")
         ), \
         patch.object(s.offline_backend, "is_available", return_value=False), \
         patch("speech.time.sleep"):
        result = s.listen()

    assert result == ""
    assert "trouble connecting" in voice.spoken[-1]
    # END test_offline_backend_unavailable_falls_through_like_before_phase_10_1


# =======================================================================
# PHASE 11.4: Urdu STT fallback (ur-PK). config.ENABLE_URDU_STT_FALLBACK
# default False; reachable ONLY from the SpeechUnintelligible branch of
# _recognize() - never from RecognitionNetworkError (see stt_backend.py
# for why: a failed network/API call carries no information about the
# audio's language, and config.SPEECH_API_RETRIES already owns retrying
# that failure on the same audio). Section labels mirror the Phase 11.4
# spec's A-K test matrix.
# =======================================================================

# ---- A. Flag defaults False; existing behavior with the flag False is
# byte-for-byte unchanged. ----

def test_urdu_stt_fallback_flag_defaults_false():
    assert config.ENABLE_URDU_STT_FALLBACK is False


def test_flag_false_preserves_existing_unknown_value_behavior():
    """With the flag at its default (False), UnknownValueError behavior
    is identical to pre-Phase-11.4: exactly one recognize_google() call,
    straight to the offline fallback, no Urdu attempt at all."""

    s, voice = make_speech()
    fake_audio = object()

    with patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio), \
         patch.object(
             s.recognizer, "recognize_google",
             side_effect=sr.UnknownValueError()
         ) as mock_recognize, \
         patch.object(s.offline_backend, "is_available", return_value=True), \
         patch.object(
             s.offline_backend, "recognize", return_value="set volume to 40"
         ):
        result = s.listen()

    assert result == "set volume to 40"
    assert mock_recognize.call_count == 1


# ---- B. English success - Urdu is never attempted. ----

def test_english_success_never_attempts_urdu():
    s, voice = make_speech()
    fake_audio = object()

    with patch.object(config, "ENABLE_URDU_STT_FALLBACK", True), \
         patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio), \
         patch.object(
             s.recognizer, "recognize_google", return_value="Open Chrome"
         ) as mock_recognize:
        result = s.listen()

    assert result == "open chrome"
    mock_recognize.assert_called_once()
    assert mock_recognize.call_args.kwargs["language"] == "en-US"


# ---- C. English UnknownValueError + flag ON - Urdu attempted, second
# call uses language="ur-PK", same AudioData object. ----

def test_english_unknown_value_error_with_flag_on_attempts_urdu():
    s, voice = make_speech()
    fake_audio = object()

    with patch.object(config, "ENABLE_URDU_STT_FALLBACK", True), \
         patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio), \
         patch.object(
             s.recognizer, "recognize_google",
             side_effect=[sr.UnknownValueError(), "Urdu Text"],
         ) as mock_recognize:
        result = s.listen()

    assert result == "urdu text"
    assert mock_recognize.call_count == 2

    first_call, second_call = mock_recognize.call_args_list
    assert first_call.kwargs["language"] == "en-US"
    assert second_call.kwargs["language"] == "ur-PK"
    assert first_call.args[0] is fake_audio
    assert second_call.args[0] is fake_audio


# ---- D. English UnknownValueError + flag OFF - Urdu never attempted;
# existing offline fallback behavior unchanged. ----

def test_english_unknown_value_error_with_flag_off_skips_urdu():
    s, voice = make_speech()
    fake_audio = object()

    with patch.object(config, "ENABLE_URDU_STT_FALLBACK", False), \
         patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio), \
         patch.object(
             s.recognizer, "recognize_google",
             side_effect=sr.UnknownValueError()
         ) as mock_recognize, \
         patch.object(s.offline_backend, "is_available", return_value=True), \
         patch.object(
             s.offline_backend, "recognize", return_value="open chrome"
         ) as mock_offline:
        result = s.listen()

    assert result == "open chrome"
    assert mock_recognize.call_count == 1
    mock_offline.assert_called_once()


# ---- E. Urdu success - Speech.listen() returns the Urdu text; offline
# fallback is never attempted after a successful Urdu recognition. ----

def test_urdu_success_returns_urdu_text_without_offline_fallback():
    s, voice = make_speech()
    fake_audio = object()

    with patch.object(config, "ENABLE_URDU_STT_FALLBACK", True), \
         patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio), \
         patch.object(
             s.recognizer, "recognize_google",
             side_effect=[sr.UnknownValueError(), "Kholo Chrome"],
         ), \
         patch.object(s.offline_backend, "is_available") as mock_available, \
         patch.object(s.offline_backend, "recognize") as mock_offline_recognize:
        result = s.listen()

    assert result == "kholo chrome"
    mock_available.assert_not_called()
    mock_offline_recognize.assert_not_called()


# ---- F. Urdu UnknownValueError - existing offline fallback continues;
# no additional Urdu retry occurs. ----

def test_urdu_unknown_value_error_falls_through_to_offline_no_retry():
    s, voice = make_speech()
    fake_audio = object()

    with patch.object(config, "ENABLE_URDU_STT_FALLBACK", True), \
         patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio), \
         patch.object(
             s.recognizer, "recognize_google",
             side_effect=[sr.UnknownValueError(), sr.UnknownValueError()],
         ) as mock_recognize, \
         patch.object(s.offline_backend, "is_available", return_value=True), \
         patch.object(
             s.offline_backend, "recognize", return_value="mute"
         ) as mock_offline:
        result = s.listen()

    assert result == "mute"
    # Exactly two recognize_google calls (English + ONE Urdu attempt) -
    # no additional Urdu retry loop.
    assert mock_recognize.call_count == 2
    mock_offline.assert_called_once()


# ---- G. RequestError - existing SPEECH_API_RETRIES behavior is
# unchanged; Urdu is NEVER attempted, even with the flag on. ----

def test_request_error_never_attempts_urdu_even_with_flag_on():
    s, voice = make_speech()
    fake_audio = object()

    with patch.object(config, "ENABLE_URDU_STT_FALLBACK", True), \
         patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio), \
         patch.object(
             s.recognizer, "recognize_google",
             side_effect=sr.RequestError("boom")
         ) as mock_recognize, \
         patch("speech.time.sleep"):
        result = s.listen()

    assert result == ""
    # Exactly 1 + SPEECH_API_RETRIES calls - the existing, unmodified
    # English-only retry behavior - never a "ur-PK" call anywhere.
    assert mock_recognize.call_count == 1 + config.SPEECH_API_RETRIES
    for call in mock_recognize.call_args_list:
        assert call.kwargs["language"] == "en-US"
    assert "trouble connecting" in voice.spoken[-1]


# ---- H. Same AudioData identity across English -> Urdu -> offline;
# microphone captured exactly once. ----

def test_same_audio_data_object_used_across_english_urdu_and_offline():
    s, voice = make_speech()
    sentinel_audio = object()

    with patch.object(config, "ENABLE_URDU_STT_FALLBACK", True), \
         patch("speech.sr.Microphone"), \
         patch.object(
             s.recognizer, "listen", return_value=sentinel_audio
         ) as mock_listen, \
         patch.object(
             s.recognizer, "recognize_google",
             side_effect=[sr.UnknownValueError(), sr.UnknownValueError()],
         ) as mock_recognize, \
         patch.object(s.offline_backend, "is_available", return_value=True), \
         patch.object(
             s.offline_backend, "recognize", return_value="open chrome"
         ) as mock_offline:
        s.listen()

    mock_listen.assert_called_once()

    for call in mock_recognize.call_args_list:
        assert call.args[0] is sentinel_audio

    mock_offline.assert_called_once()
    assert mock_offline.call_args.args[1] is sentinel_audio


def test_try_urdu_fallback_never_recaptures_microphone():
    """Direct unit test of _try_urdu_fallback() in isolation: it must
    call urdu_online_backend.recognize() with the audio it was given -
    and must never construct sr.Microphone() or call recognizer.
    listen() itself."""

    s, voice = make_speech()
    fake_audio = object()

    with patch("speech.sr.Microphone") as mock_mic_class, \
         patch.object(s.recognizer, "listen") as mock_listen, \
         patch.object(
             s.urdu_online_backend, "recognize", return_value="urdu text"
         ) as mock_urdu_recognize:
        result = s._try_urdu_fallback(fake_audio)

    assert result == "urdu text"
    mock_urdu_recognize.assert_called_once_with(s.recognizer, fake_audio)
    mock_mic_class.assert_not_called()
    mock_listen.assert_not_called()


def test_try_urdu_fallback_returns_empty_string_on_unknown_value_error():
    s, voice = make_speech()

    with patch.object(
        s.urdu_online_backend, "recognize",
        side_effect=stt_backend.SpeechUnintelligible()
    ):
        result = s._try_urdu_fallback(object())

    assert result == ""


def test_try_urdu_fallback_returns_empty_string_on_network_error():
    s, voice = make_speech()

    with patch.object(
        s.urdu_online_backend, "recognize",
        side_effect=stt_backend.RecognitionNetworkError("boom")
    ):
        result = s._try_urdu_fallback(object())

    assert result == ""


def test_try_urdu_fallback_makes_exactly_one_attempt_no_retry_loop():
    s, voice = make_speech()

    with patch.object(
        s.urdu_online_backend, "recognize",
        side_effect=stt_backend.RecognitionNetworkError("boom")
    ) as mock_urdu_recognize:
        s._try_urdu_fallback(object())

    mock_urdu_recognize.assert_called_once()


# ---- I. Exactly one final result reaches the caller - the invariant
# that keeps commands.CommandProcessor.process() from ever being handed
# two competing (English/Urdu) interpretations of one utterance.
# commands.py is not touched by this phase; this proves the invariant
# holds at its source. ----

def test_listen_returns_single_string_result_on_urdu_fallback():
    s, voice = make_speech()
    fake_audio = object()

    with patch.object(config, "ENABLE_URDU_STT_FALLBACK", True), \
         patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio), \
         patch.object(
             s.recognizer, "recognize_google",
             side_effect=[sr.UnknownValueError(), "urdu result"],
         ):
        result = s.listen()

    assert isinstance(result, str)
    assert result == "urdu result"


# ---- Backend wiring sanity: the Speech object's second backend
# instance is fixed to the Urdu language code. ----

def test_speech_constructs_urdu_online_backend_with_urdu_language():
    s, voice = make_speech()
    assert s.urdu_online_backend.language == config.URDU_RECOGNITION_LANGUAGE
    assert s.urdu_online_backend.language == "ur-PK"


# =======================================================================
# PHASE 11.9 (Step 5): ambient-noise calibration duration - raised from
# 1.0 to 2.0 based on measured Phase 11.8 live-session evidence (see
# config.py's own comment for the two calibration values that motivated
# this).
# =======================================================================

def test_ambient_noise_duration_raised_to_two_seconds():
    assert config.AMBIENT_NOISE_DURATION == 2.0


def test_calibrate_microphone_uses_configured_ambient_noise_duration():
    s, voice = make_speech()

    with patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "adjust_for_ambient_noise") as mock_adjust:
        s.calibrate_microphone()

    mock_adjust.assert_called_once()
    assert mock_adjust.call_args.kwargs["duration"] == config.AMBIENT_NOISE_DURATION


# =======================================================================
# PHASE 11.9 (Step 6): diagnostics - config.DEBUG-gated console output
# only (no new mode, no raw audio ever persisted). Every test here
# proves these diagnostics never raise and never block normal
# operation, regardless of config.DEBUG.
# =======================================================================

def test_audio_duration_seconds_computes_from_declared_sample_rate():
    class FakeAudio:
        frame_data = b"\x00" * 32000  # 16000 Hz * 2 bytes/sample * 1s
        sample_width = 2
        sample_rate = 16000

    assert speech_module._audio_duration_seconds(FakeAudio()) == 1.0


def test_audio_duration_seconds_never_raises_on_malformed_audio():
    assert speech_module._audio_duration_seconds(object()) == 0.0
    assert speech_module._audio_duration_seconds(None) == 0.0

    class ZeroRate:
        frame_data = b"\x00\x00"
        sample_width = 2
        sample_rate = 0

    assert speech_module._audio_duration_seconds(ZeroRate()) == 0.0


def test_describe_microphone_never_raises_with_explicit_device_index():
    fake_source = type("FakeSource", (), {"device_index": 0})()

    with patch(
        "speech.sr.Microphone.list_microphone_names",
        return_value=["Test Microphone"],
    ):
        description = speech_module._describe_microphone(fake_source)

    assert "Test Microphone" in description


def test_describe_microphone_never_raises_when_index_out_of_range():
    fake_source = type("FakeSource", (), {"device_index": 999})()

    with patch(
        "speech.sr.Microphone.list_microphone_names",
        return_value=["Only One Device"],
    ):
        description = speech_module._describe_microphone(fake_source)

    assert "999" in description


def test_describe_microphone_never_raises_when_names_lookup_fails():
    fake_source = type("FakeSource", (), {"device_index": 3})()

    with patch(
        "speech.sr.Microphone.list_microphone_names",
        side_effect=OSError("no audio subsystem"),
    ):
        description = speech_module._describe_microphone(fake_source)

    assert "3" in description


def test_describe_microphone_resolves_default_device_when_index_is_none():
    fake_source = type("FakeSource", (), {"device_index": None})()

    fake_pyaudio_module = type("FakePyAudioModule", (), {})()

    class FakePyAudio:
        def get_default_input_device_info(self):
            return {"index": 1, "name": "Default Mic"}

        def terminate(self):
            pass

    fake_pyaudio_module.PyAudio = FakePyAudio

    with patch.dict("sys.modules", {"pyaudio": fake_pyaudio_module}):
        description = speech_module._describe_microphone(fake_source)

    assert "Default Mic" in description


def test_describe_microphone_never_raises_when_pyaudio_lookup_fails():
    fake_source = type("FakeSource", (), {"device_index": None})()

    fake_pyaudio_module = type("FakePyAudioModule", (), {})()

    class FakePyAudio:
        def get_default_input_device_info(self):
            raise OSError("no default device")

        def terminate(self):
            pass

    fake_pyaudio_module.PyAudio = FakePyAudio

    with patch.dict("sys.modules", {"pyaudio": fake_pyaudio_module}):
        description = speech_module._describe_microphone(fake_source)

    assert isinstance(description, str)


def test_calibrate_microphone_debug_diagnostics_never_raise():
    """config.DEBUG=True must not change calibration behavior or crash
    it - only add console diagnostics."""

    s, voice = make_speech()

    with patch.object(config, "DEBUG", True), \
         patch("speech.sr.Microphone") as mock_mic_cls, \
         patch.object(s.recognizer, "adjust_for_ambient_noise"):

        mock_mic_cls.return_value.__enter__.return_value = type(
            "FakeSource", (), {"device_index": None}
        )()

        s.calibrate_microphone()


def test_capture_audio_debug_diagnostics_never_raise_on_success():
    s, voice = make_speech()
    fake_audio = type(
        "FakeAudio", (), {"frame_data": b"\x00" * 100, "sample_width": 2, "sample_rate": 16000}
    )()

    with patch.object(config, "DEBUG", True), \
         patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio):
        result = s._capture_audio(timeout=3, phrase_limit=5)

    assert result is fake_audio


def test_capture_audio_debug_diagnostics_never_raise_on_timeout():
    s, voice = make_speech()

    with patch.object(config, "DEBUG", True), \
         patch("speech.sr.Microphone"), \
         patch.object(
             s.recognizer, "listen", side_effect=sr.WaitTimeoutError()
         ):
        result = s._capture_audio(timeout=3, phrase_limit=5)

    assert result is None


def test_capture_audio_debug_off_produces_no_diagnostic_prints(capsys):
    """Default config.DEBUG=False must not print any [DEBUG] lines -
    diagnostics are strictly opt-in, adding zero console noise by
    default."""

    s, voice = make_speech()
    fake_audio = object()

    with patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio):
        s._capture_audio(timeout=3, phrase_limit=5)

    captured = capsys.readouterr()
    assert "[DEBUG]" not in captured.out


# =======================================================================
# PHASE 11.11 (Step 3): deterministic diagnostics - Speech.
# last_diagnostics. Every test here asserts on the STRUCTURED dict
# directly, never by parsing console output - this is what "Build
# deterministic diagnostics" (Phase 11.11 Step 3) means in practice.
# listen()'s own return-value contract (a plain string) is completely
# unchanged throughout - last_diagnostics is purely additive.
# =======================================================================

def test_diagnostics_default_shape_before_any_listen_call():
    s, voice = make_speech()
    d = s.last_diagnostics

    assert d["audio_captured"] is False
    assert d["google_attempted"] is False
    assert d["google_result"] is None
    assert d["whisper_invoked"] is False
    assert d["final_result"] == ""
    assert d["final_source"] is None


def test_diagnostics_google_success_case():
    s, voice = make_speech()
    fake_audio = object()

    with patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio), \
         patch.object(
             s.recognizer, "recognize_google", return_value="Open Chrome"
         ):
        s.listen()

    d = s.last_diagnostics
    assert d["audio_captured"] is True
    assert d["google_attempted"] is True
    assert d["google_result"] == "open chrome"
    assert d["google_error"] is None
    assert d["whisper_invoked"] is False
    assert d["final_source"] == "google"
    assert d["final_result"] == "open chrome"


def test_diagnostics_google_unintelligible_then_offline_success():
    s, voice = make_speech()
    fake_audio = object()

    with patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio), \
         patch.object(
             s.recognizer, "recognize_google",
             side_effect=sr.UnknownValueError()
         ), \
         patch.object(s.offline_backend, "is_available", return_value=True), \
         patch.object(
             s.offline_backend, "recognize", return_value="mute"
         ):
        s.listen()

    d = s.last_diagnostics
    assert d["google_attempted"] is True
    assert d["google_error"] == "unintelligible"
    assert d["whisper_invoked"] is True
    assert d["whisper_result"] == "mute"
    assert d["final_source"] == "offline_whisper"
    assert d["final_result"] == "mute"


def test_diagnostics_google_unintelligible_then_offline_also_fails():
    s, voice = make_speech()
    fake_audio = object()

    with patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio), \
         patch.object(
             s.recognizer, "recognize_google",
             side_effect=sr.UnknownValueError()
         ), \
         patch.object(s.offline_backend, "is_available", return_value=True), \
         patch.object(
             s.offline_backend, "recognize",
             side_effect=stt_backend.SpeechUnintelligible()
         ):
        s.listen()

    d = s.last_diagnostics
    assert d["whisper_invoked"] is True
    assert d["whisper_result"] is None
    assert d["final_source"] is None
    assert d["final_result"] == ""


def test_diagnostics_network_error_records_error_type():
    s, voice = make_speech()
    fake_audio = object()

    with patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio), \
         patch.object(
             s.recognizer, "recognize_google",
             side_effect=sr.RequestError("boom")
         ), \
         patch("speech.time.sleep"):
        s.listen()

    assert s.last_diagnostics["google_error"] == "network_error"


def test_diagnostics_timeout_never_attempts_recognition():
    s, voice = make_speech()

    with patch("speech.sr.Microphone"), \
         patch.object(
             s.recognizer, "listen", side_effect=sr.WaitTimeoutError()
         ):
        s.listen()

    d = s.last_diagnostics
    assert d["audio_captured"] is False
    assert d["google_attempted"] is False
    assert d["whisper_invoked"] is False
    assert d["capture_wall_time"] is not None
    assert d["final_result"] == ""


def test_diagnostics_urdu_fallback_attempted_and_succeeds():
    s, voice = make_speech()
    fake_audio = object()

    with patch.object(config, "ENABLE_URDU_STT_FALLBACK", True), \
         patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio), \
         patch.object(
             s.recognizer, "recognize_google",
             side_effect=[sr.UnknownValueError(), "urdu text"],
         ):
        s.listen()

    d = s.last_diagnostics
    assert d["urdu_attempted"] is True
    assert d["urdu_result"] == "urdu text"
    assert d["final_source"] == "urdu"
    assert d["whisper_invoked"] is False


def test_diagnostics_urdu_flag_off_never_attempts_urdu():
    s, voice = make_speech()
    fake_audio = object()

    with patch.object(config, "ENABLE_URDU_STT_FALLBACK", False), \
         patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio), \
         patch.object(
             s.recognizer, "recognize_google",
             side_effect=sr.UnknownValueError()
         ), \
         patch.object(s.offline_backend, "is_available", return_value=True), \
         patch.object(s.offline_backend, "recognize", return_value="mute"):
        s.listen()

    assert s.last_diagnostics["urdu_attempted"] is False


def test_diagnostics_reset_between_calls():
    """A stale value from a previous listen() call must never leak into
    the next call's diagnostics."""

    s, voice = make_speech()
    fake_audio = object()

    with patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio), \
         patch.object(
             s.recognizer, "recognize_google", return_value="Open Chrome"
         ):
        s.listen()

    assert s.last_diagnostics["google_result"] == "open chrome"

    with patch("speech.sr.Microphone"), \
         patch.object(
             s.recognizer, "listen", side_effect=sr.WaitTimeoutError()
         ):
        s.listen()

    d = s.last_diagnostics
    assert d["google_result"] is None
    assert d["audio_captured"] is False


# ---- Whisper confidence gate wired end-to-end through Speech.listen() ----

def test_diagnostics_whisper_confidence_rejection_end_to_end():
    """Gate ON: a hallucinated Whisper transcription (low confidence)
    must not become listen()'s return value - listen() must return ""
    exactly as if nothing had been understood at all, and last_
    diagnostics must record the rejection."""

    s, voice = make_speech()
    fake_audio = object()

    with patch.object(config, "ENABLE_WHISPER_CONFIDENCE_GATE", True), \
         patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio), \
         patch.object(
             s.recognizer, "recognize_google",
             side_effect=sr.UnknownValueError()
         ), \
         patch.object(s.offline_backend, "is_available", return_value=True), \
         patch.object(
             s.offline_backend, "last_confidence", (0.95, -5.0)
         ), \
         patch.object(
             s.offline_backend, "recognize",
             side_effect=stt_backend.SpeechUnintelligible()
         ):
        result = s.listen()

    assert result == ""
    d = s.last_diagnostics
    assert d["whisper_invoked"] is True
    assert d["whisper_result"] is None
    assert d["whisper_rejected_low_confidence"] is True
    assert d["final_result"] == ""


def test_diagnostics_whisper_confidence_gate_off_no_rejection_flag():
    s, voice = make_speech()
    fake_audio = object()

    assert config.ENABLE_WHISPER_CONFIDENCE_GATE is False

    with patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio), \
         patch.object(
             s.recognizer, "recognize_google",
             side_effect=sr.UnknownValueError()
         ), \
         patch.object(s.offline_backend, "is_available", return_value=True), \
         patch.object(
             s.offline_backend, "last_confidence", (0.95, -5.0)
         ), \
         patch.object(
             s.offline_backend, "recognize",
             side_effect=stt_backend.SpeechUnintelligible()
         ):
        s.listen()

    assert s.last_diagnostics["whisper_rejected_low_confidence"] is False


# ---- Unicode transcription safety at the Speech level ----

def test_listen_returns_unicode_google_result_without_raising():
    s, voice = make_speech()
    fake_audio = object()

    with patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio), \
         patch.object(
             s.recognizer, "recognize_google", return_value="کمپیوٹر بند کرو"
         ):
        result = s.listen()

    assert result == "کمپیوٹر بند کرو"
    assert s.last_diagnostics["google_result"] == "کمپیوٹر بند کرو"


def test_listen_returns_unicode_offline_result_without_raising():
    s, voice = make_speech()
    fake_audio = object()

    with patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio), \
         patch.object(
             s.recognizer, "recognize_google",
             side_effect=sr.UnknownValueError()
         ), \
         patch.object(s.offline_backend, "is_available", return_value=True), \
         patch.object(
             s.offline_backend, "recognize", return_value="そんなに"
         ):
        result = s.listen()

    assert result == "そんなに"
