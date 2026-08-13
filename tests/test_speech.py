from unittest.mock import patch

import speech_recognition as sr

import config
import speech as speech_module


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
