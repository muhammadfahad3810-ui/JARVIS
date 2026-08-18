from unittest.mock import Mock, patch

import voice


def _patched_pyttsx3(mock_engine=None):
    engine = mock_engine or Mock()
    return patch("voice.pyttsx3.init", return_value=engine), engine


# ---------------------------------------------------------------------
# Backend selection at construction time
# ---------------------------------------------------------------------

def test_voice_uses_pyttsx3_only_when_backend_config_is_pyttsx3():
    """config.TTS_BACKEND == "pyttsx3" must skip the neural backend
    entirely and reproduce the exact original (pre-11.13) behavior."""
    patcher, engine = _patched_pyttsx3()

    with patcher, patch("voice.config.TTS_BACKEND", "pyttsx3"), \
         patch("voice.tts_backend.KokoroBackend") as mock_backend_cls:
        v = voice.Voice()

    mock_backend_cls.assert_not_called()
    assert v._neural_backend is None


def test_voice_selects_kokoro_backend_when_available():
    patcher, engine = _patched_pyttsx3()
    fake_backend = Mock()
    fake_backend.is_available.return_value = True

    with patcher, patch("voice.config.TTS_BACKEND", "kokoro"), \
         patch("voice.tts_backend.KokoroBackend", return_value=fake_backend):
        v = voice.Voice()

    assert v._neural_backend is fake_backend


def test_voice_has_no_neural_backend_when_kokoro_unavailable():
    """The normal, expected case before the model files are downloaded
    - see tts_backend.KokoroBackend.is_available()."""
    patcher, engine = _patched_pyttsx3()
    fake_backend = Mock()
    fake_backend.is_available.return_value = False

    with patcher, patch("voice.config.TTS_BACKEND", "kokoro"), \
         patch("voice.tts_backend.KokoroBackend", return_value=fake_backend):
        v = voice.Voice()

    assert v._neural_backend is None


def test_voice_construction_never_raises_if_is_available_itself_raises():
    """A broken optional dependency must never prevent Voice.__init__()
    from succeeding - no crash when TTS is unavailable."""
    patcher, engine = _patched_pyttsx3()
    fake_backend = Mock()
    fake_backend.is_available.side_effect = RuntimeError("boom")

    with patcher, patch("voice.config.TTS_BACKEND", "kokoro"), \
         patch("voice.tts_backend.KokoroBackend", return_value=fake_backend):
        v = voice.Voice()  # must not raise

    assert v._neural_backend is None


def test_voice_pyttsx3_engine_still_initialized_even_with_neural_backend():
    """The pyttsx3 engine must always be constructed - it's the
    unconditional fallback - regardless of whether a neural backend is
    also selected."""
    patcher, engine = _patched_pyttsx3()
    fake_backend = Mock()
    fake_backend.is_available.return_value = True

    with patcher as mock_init, \
         patch("voice.config.TTS_BACKEND", "kokoro"), \
         patch("voice.tts_backend.KokoroBackend", return_value=fake_backend):
        voice.Voice()

    mock_init.assert_called_once()
    engine.setProperty.assert_any_call("rate", voice.config.TTS_RATE)
    engine.setProperty.assert_any_call("volume", voice.config.TTS_VOLUME)


# ---------------------------------------------------------------------
# speak() - neural backend success path
# ---------------------------------------------------------------------

def _make_voice_with_neural_backend(fake_backend):
    patcher, engine = _patched_pyttsx3()
    with patcher, patch("voice.config.TTS_BACKEND", "kokoro"), \
         patch("voice.tts_backend.KokoroBackend", return_value=fake_backend):
        v = voice.Voice()
    return v, engine


def test_speak_uses_neural_backend_when_available_and_skips_pyttsx3():
    fake_backend = Mock()
    fake_backend.is_available.return_value = True
    v, engine = _make_voice_with_neural_backend(fake_backend)

    v.speak("Opening Chrome.")

    fake_backend.speak.assert_called_once_with(
        "Opening Chrome.",
        voice=voice.config.TTS_VOICE,
        speed=voice.config.TTS_SPEED,
        volume=voice.config.TTS_VOLUME,
    )
    engine.say.assert_not_called()
    engine.runAndWait.assert_not_called()


def test_speak_prints_the_response_regardless_of_backend(capsys):
    fake_backend = Mock()
    fake_backend.is_available.return_value = True
    v, engine = _make_voice_with_neural_backend(fake_backend)

    v.speak("Going offline. Goodbye.")

    assert "JARVIS: Going offline. Goodbye." in capsys.readouterr().out


# ---------------------------------------------------------------------
# speak() - fallback to pyttsx3 (no crash when TTS is unavailable)
# ---------------------------------------------------------------------

def test_speak_falls_back_to_pyttsx3_when_neural_backend_raises():
    fake_backend = Mock()
    fake_backend.is_available.return_value = True
    fake_backend.speak.side_effect = RuntimeError("synthesis failed")
    v, engine = _make_voice_with_neural_backend(fake_backend)

    v.speak("Yes?")  # must not raise

    engine.say.assert_called_once_with("Yes?")
    engine.runAndWait.assert_called_once()


def test_speak_uses_pyttsx3_directly_when_no_neural_backend_selected():
    fake_backend = Mock()
    fake_backend.is_available.return_value = False
    v, engine = _make_voice_with_neural_backend(fake_backend)

    v.speak("I didn't understand that. Please try again.")

    fake_backend.speak.assert_not_called()
    engine.say.assert_called_once_with(
        "I didn't understand that. Please try again."
    )
    engine.runAndWait.assert_called_once()


def test_speak_never_raises_even_on_repeated_neural_failures():
    fake_backend = Mock()
    fake_backend.is_available.return_value = True
    fake_backend.speak.side_effect = OSError("no audio device")
    v, engine = _make_voice_with_neural_backend(fake_backend)

    v.speak("first")
    v.speak("second")  # must not raise either time

    assert engine.say.call_count == 2
