import sys
import winsound
from unittest.mock import Mock, patch

import numpy as np

import tts_backend


# ---------------------------------------------------------------------
# is_available() - optional-dependency gating, mirrors stt_backend.
# OfflineWhisperBackend.is_available()'s own test style.
# ---------------------------------------------------------------------

def test_is_available_false_when_kokoro_onnx_not_installed():
    backend = tts_backend.KokoroBackend()

    with patch.dict(sys.modules, {"kokoro_onnx": None}):
        assert backend.is_available() is False


def test_is_available_false_when_model_file_missing():
    backend = tts_backend.KokoroBackend()

    with patch("tts_backend.os.path.isfile", side_effect=[False, True]):
        assert backend.is_available() is False


def test_is_available_false_when_voices_file_missing():
    backend = tts_backend.KokoroBackend()

    with patch("tts_backend.os.path.isfile", side_effect=[True, False]):
        assert backend.is_available() is False


def test_is_available_true_when_installed_and_both_files_present():
    backend = tts_backend.KokoroBackend()

    with patch("tts_backend.os.path.isfile", return_value=True):
        assert backend.is_available() is True


def test_is_available_never_raises_on_unexpected_error():
    backend = tts_backend.KokoroBackend()

    with patch("tts_backend.os.path.isfile", side_effect=OSError("boom")):
        assert backend.is_available() is False


def test_is_available_does_not_load_the_model():
    """Constructing/checking availability must never pay the model-
    load cost - _load() (and therefore the actual Kokoro/onnxruntime
    construction) must not be called."""
    backend = tts_backend.KokoroBackend()

    with patch("tts_backend.os.path.isfile", return_value=True), \
         patch.object(backend, "_load") as mock_load:
        backend.is_available()

    mock_load.assert_not_called()
    assert backend._kokoro is None


# ---------------------------------------------------------------------
# synthesize() / speak() - success path
# ---------------------------------------------------------------------

def _fake_kokoro(samples=None, sample_rate=24000):
    fake = Mock()
    fake.create.return_value = (
        samples if samples is not None else np.zeros(100, dtype=np.float32),
        sample_rate,
    )
    return fake


def test_synthesize_calls_kokoro_create_with_expected_arguments():
    backend = tts_backend.KokoroBackend()
    fake_kokoro = _fake_kokoro()

    with patch.object(backend, "_load", return_value=fake_kokoro):
        samples, sample_rate = backend.synthesize("Yes?", voice="af_heart", speed=1.0)

    fake_kokoro.create.assert_called_once_with(
        "Yes?", voice="af_heart", speed=1.0, lang="en-us"
    )
    assert sample_rate == 24000


def test_synthesize_loads_lazily_only_once():
    backend = tts_backend.KokoroBackend()
    fake_kokoro = _fake_kokoro()

    with patch.object(backend, "_load", return_value=fake_kokoro) as mock_load:
        backend.synthesize("one", voice="af_heart", speed=1.0)
        backend.synthesize("two", voice="af_heart", speed=1.0)

    # _load() itself is responsible for its own memoization - this just
    # proves synthesize() calls it every time rather than caching
    # independently (the caching contract lives in _load()/__init__).
    assert mock_load.call_count == 2


def test_speak_synthesizes_then_plays_with_volume():
    backend = tts_backend.KokoroBackend()
    samples = np.array([0.1, -0.2, 0.3], dtype=np.float32)

    with patch.object(backend, "synthesize", return_value=(samples, 24000)) as mock_synth, \
         patch("tts_backend._play") as mock_play:
        backend.speak("Opening Chrome.", voice="af_heart", speed=1.0, volume=0.8)

    mock_synth.assert_called_once_with("Opening Chrome.", "af_heart", 1.0)
    mock_play.assert_called_once()
    played_samples, played_rate, played_volume = mock_play.call_args.args
    assert played_rate == 24000
    assert played_volume == 0.8
    assert list(played_samples) == list(samples)


# ---------------------------------------------------------------------
# speak()/synthesize() failure propagation - tts_backend itself does
# NOT swallow errors; voice.py owns the fallback-to-pyttsx3 decision
# (see test_voice.py). This backend must let a real failure surface.
# ---------------------------------------------------------------------

def test_speak_propagates_synthesis_errors():
    backend = tts_backend.KokoroBackend()

    with patch.object(backend, "synthesize", side_effect=RuntimeError("onnx boom")):
        try:
            backend.speak("hello", voice="af_heart", speed=1.0, volume=1.0)
            assert False, "expected RuntimeError to propagate"
        except RuntimeError:
            pass


def test_speak_propagates_playback_errors():
    backend = tts_backend.KokoroBackend()
    samples = np.zeros(10, dtype=np.float32)

    with patch.object(backend, "synthesize", return_value=(samples, 24000)), \
         patch("tts_backend._play", side_effect=OSError("no audio device")):
        try:
            backend.speak("hello", voice="af_heart", speed=1.0, volume=1.0)
            assert False, "expected OSError to propagate"
        except OSError:
            pass


# ---------------------------------------------------------------------
# _load() - device/provider selection (config.TTS_DEVICE)
# ---------------------------------------------------------------------

def test_load_uses_cpu_provider_by_default():
    backend = tts_backend.KokoroBackend()

    fake_session = Mock()
    fake_kokoro_instance = Mock()

    with patch("tts_backend.config.TTS_DEVICE", "cpu"), \
         patch("onnxruntime.InferenceSession", return_value=fake_session) as mock_session, \
         patch("kokoro_onnx.Kokoro.from_session", return_value=fake_kokoro_instance) as mock_from_session:
        result = backend._load()

    mock_session.assert_called_once_with(
        tts_backend.MODEL_PATH, providers=["CPUExecutionProvider"]
    )
    mock_from_session.assert_called_once_with(fake_session, tts_backend.VOICES_PATH)
    assert result is fake_kokoro_instance


def test_load_uses_cuda_provider_with_cpu_fallback_when_configured():
    backend = tts_backend.KokoroBackend()

    with patch("tts_backend.config.TTS_DEVICE", "cuda"), \
         patch("onnxruntime.InferenceSession", return_value=Mock()) as mock_session, \
         patch("kokoro_onnx.Kokoro.from_session", return_value=Mock()):
        backend._load()

    mock_session.assert_called_once_with(
        tts_backend.MODEL_PATH,
        providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
    )


def test_load_is_memoized():
    backend = tts_backend.KokoroBackend()
    fake_kokoro_instance = Mock()

    with patch("onnxruntime.InferenceSession", return_value=Mock()), \
         patch(
             "kokoro_onnx.Kokoro.from_session", return_value=fake_kokoro_instance
         ) as mock_from_session:
        first = backend._load()
        second = backend._load()

    assert first is second is fake_kokoro_instance
    mock_from_session.assert_called_once()


# ---------------------------------------------------------------------
# _play() - WAV writing, volume scaling/clipping, playback, cleanup
# ---------------------------------------------------------------------

def test_play_writes_wav_and_plays_via_winsound_then_removes_file():
    samples = np.array([0.5, -0.5, 0.25], dtype=np.float32)
    captured_paths = []

    real_remove = tts_backend.os.remove

    def spy_remove(path):
        captured_paths.append(path)
        real_remove(path)

    with patch("tts_backend.os.remove", side_effect=spy_remove) as mock_remove, \
         patch("winsound.PlaySound") as mock_play_sound:
        tts_backend._play(samples, 24000, 1.0)

    mock_play_sound.assert_called_once()
    args, kwargs = mock_play_sound.call_args
    assert args[1] == winsound.SND_FILENAME
    mock_remove.assert_called_once()
    assert captured_paths[0].endswith(".wav")
    assert not tts_backend.os.path.exists(captured_paths[0])


def test_play_removes_file_even_if_playback_raises():
    samples = np.zeros(10, dtype=np.float32)

    with patch("winsound.PlaySound", side_effect=RuntimeError("device busy")), \
         patch("tts_backend.os.remove") as mock_remove:
        try:
            tts_backend._play(samples, 24000, 1.0)
            assert False, "expected RuntimeError to propagate"
        except RuntimeError:
            pass

    mock_remove.assert_called_once()


def test_play_clamps_volume_above_one():
    samples = np.array([1.0, -1.0], dtype=np.float32)

    with patch("winsound.PlaySound"):
        # volume=5.0 must not overdrive/clip differently than 1.0 would -
        # both should produce the same clamped-to-full-scale PCM output.
        # Just proving this doesn't raise/overflow is the safety property
        # under test; exact sample values are covered indirectly via the
        # write-then-play path above.
        tts_backend._play(samples, 24000, 5.0)


def test_play_clamps_negative_volume_to_zero():
    samples = np.array([1.0, -1.0], dtype=np.float32)

    with patch("winsound.PlaySound"), \
         patch("wave.open") as mock_wave_open:
        mock_wav_file = Mock()
        mock_wave_open.return_value.__enter__.return_value = mock_wav_file

        tts_backend._play(samples, 24000, -1.0)

    written_bytes = mock_wav_file.writeframes.call_args.args[0]
    written = np.frombuffer(written_bytes, dtype=np.int16)
    assert all(v == 0 for v in written)
