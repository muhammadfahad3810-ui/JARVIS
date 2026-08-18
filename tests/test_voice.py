import threading
import time
from unittest.mock import Mock, patch

import config
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


# ---------------------------------------------------------------------
# Phase 11.14: TTS initialization - warm_up() called once at startup
# ---------------------------------------------------------------------

def test_voice_init_warms_up_the_neural_backend():
    fake_backend = Mock()
    fake_backend.is_available.return_value = True

    _make_voice_with_neural_backend(fake_backend)

    fake_backend.warm_up.assert_called_once()


def test_warm_up_happens_before_any_speak_call():
    """The whole point of warming up at init time - by the time the
    FIRST speak() call happens, the model must already be loaded, so
    speak() itself never triggers a load."""
    fake_backend = Mock()
    fake_backend.is_available.return_value = True
    calls = []
    fake_backend.warm_up.side_effect = lambda: calls.append("warm_up")
    fake_backend.speak.side_effect = lambda *a, **k: calls.append("speak")

    v, engine = _make_voice_with_neural_backend(fake_backend)
    v.speak("Yes?")

    assert calls == ["warm_up", "speak"]


def test_voice_falls_back_to_pyttsx3_for_the_whole_session_if_warm_up_fails():
    """warm_up() failing must disable the neural backend entirely for
    this Voice instance - not retry on every speak() call - matching
    tts_backend.KokoroBackend.warm_up()'s own documented contract."""
    patcher, engine = _patched_pyttsx3()
    fake_backend = Mock()
    fake_backend.is_available.return_value = True
    fake_backend.warm_up.side_effect = RuntimeError("model load failed")

    with patcher, patch("voice.config.TTS_BACKEND", "kokoro"), \
         patch("voice.tts_backend.KokoroBackend", return_value=fake_backend):
        v = voice.Voice()

    assert v._neural_backend is None

    v.speak("hello")

    fake_backend.speak.assert_not_called()
    engine.say.assert_called_once_with("hello")


def test_voice_init_sweeps_orphaned_temp_files():
    patcher, engine = _patched_pyttsx3()

    with patcher, patch("voice.tts_backend.cleanup_orphaned_temp_files") as mock_cleanup:
        voice.Voice()

    mock_cleanup.assert_called_once()


# ---------------------------------------------------------------------
# Phase 11.14: speech queue - speak() never overlaps, second caller
# effectively queues behind the first.
# ---------------------------------------------------------------------

def test_speak_serializes_concurrent_calls_never_overlapping():
    fake_backend = Mock()
    fake_backend.is_available.return_value = True

    intervals = []
    lock = threading.Lock()

    def fake_speak(text, **kwargs):
        start = time.monotonic()
        time.sleep(0.05)
        end = time.monotonic()
        with lock:
            intervals.append((start, end))

    fake_backend.speak.side_effect = fake_speak
    v, engine = _make_voice_with_neural_backend(fake_backend)

    threads = [
        threading.Thread(target=v.speak, args=(f"message {i}",))
        for i in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(intervals) == 4
    # No two recorded (start, end) intervals may overlap - that's the
    # "never play two audio streams simultaneously" property under test.
    intervals.sort()
    for (start1, end1), (start2, end2) in zip(intervals, intervals[1:]):
        assert end1 <= start2, "overlapping speech intervals detected"


def test_speak_queues_rather_than_drops_concurrent_calls():
    """Every concurrent speak() call must still eventually be spoken -
    "queue them" (task requirement), never silently dropped."""
    fake_backend = Mock()
    fake_backend.is_available.return_value = True
    v, engine = _make_voice_with_neural_backend(fake_backend)

    threads = [
        threading.Thread(target=v.speak, args=(f"distinct message {i}",))
        for i in range(5)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert fake_backend.speak.call_count == 5


# ---------------------------------------------------------------------
# Phase 11.14: duplicate response protection
# ---------------------------------------------------------------------

def test_speak_suppresses_immediate_exact_duplicate():
    fake_backend = Mock()
    fake_backend.is_available.return_value = True
    v, engine = _make_voice_with_neural_backend(fake_backend)

    v.speak("Pressing Enter.")
    v.speak("Pressing Enter.")

    assert fake_backend.speak.call_count == 1


def test_speak_does_not_suppress_different_text():
    fake_backend = Mock()
    fake_backend.is_available.return_value = True
    v, engine = _make_voice_with_neural_backend(fake_backend)

    v.speak("Pressing Enter.")
    v.speak("Pressing Escape.")

    assert fake_backend.speak.call_count == 2


def test_speak_does_not_suppress_duplicate_after_cooldown_expires():
    """A genuinely repeated command must never be permanently
    suppressed - only near-simultaneous accidental duplicates."""
    fake_backend = Mock()
    fake_backend.is_available.return_value = True
    v, engine = _make_voice_with_neural_backend(fake_backend)

    with patch.object(config, "DUPLICATE_SPEECH_SUPPRESS_SECONDS", 0.05):
        v.speak("Scrolling down.")
        time.sleep(0.1)
        v.speak("Scrolling down.")

    assert fake_backend.speak.call_count == 2


def test_speak_still_prints_console_line_even_when_audio_suppressed(capsys):
    fake_backend = Mock()
    fake_backend.is_available.return_value = True
    v, engine = _make_voice_with_neural_backend(fake_backend)

    v.speak("Going back.")
    v.speak("Going back.")

    output = capsys.readouterr().out
    assert output.count("JARVIS: Going back.") == 2


def test_duplicate_suppression_also_applies_to_pyttsx3_path():
    fake_backend = Mock()
    fake_backend.is_available.return_value = False
    v, engine = _make_voice_with_neural_backend(fake_backend)

    v.speak("Going forward.")
    v.speak("Going forward.")

    engine.say.assert_called_once_with("Going forward.")


# ---------------------------------------------------------------------
# Phase 11.14: stop()
# ---------------------------------------------------------------------

def test_stop_calls_pyttsx3_engine_stop():
    fake_backend = Mock()
    fake_backend.is_available.return_value = False
    v, engine = _make_voice_with_neural_backend(fake_backend)

    v.stop()

    engine.stop.assert_called_once()


def test_stop_calls_neural_backend_stop_when_present():
    fake_backend = Mock()
    fake_backend.is_available.return_value = True
    v, engine = _make_voice_with_neural_backend(fake_backend)

    v.stop()

    fake_backend.stop.assert_called_once()


def test_stop_never_raises_even_if_engine_stop_fails():
    fake_backend = Mock()
    fake_backend.is_available.return_value = True
    v, engine = _make_voice_with_neural_backend(fake_backend)
    engine.stop.side_effect = RuntimeError("boom")
    fake_backend.stop.side_effect = RuntimeError("boom too")

    v.stop()  # must not raise


def test_stop_safe_to_call_with_no_neural_backend():
    fake_backend = Mock()
    fake_backend.is_available.return_value = False
    v, engine = _make_voice_with_neural_backend(fake_backend)

    v.stop()  # must not raise

    fake_backend.stop.assert_not_called()


# ---------------------------------------------------------------------
# Phase 11.14: configuration - voice/device/speed are not hard-coded
# in more than one place.
# ---------------------------------------------------------------------

def test_speak_reads_voice_and_speed_from_config_not_hardcoded():
    fake_backend = Mock()
    fake_backend.is_available.return_value = True
    v, engine = _make_voice_with_neural_backend(fake_backend)

    with patch.object(config, "TTS_VOICE", "bf_emma"), \
         patch.object(config, "TTS_SPEED", 1.25):
        v.speak("Testing a different configured voice.")

    fake_backend.speak.assert_called_once_with(
        "Testing a different configured voice.",
        voice="bf_emma",
        speed=1.25,
        volume=config.TTS_VOLUME,
    )
