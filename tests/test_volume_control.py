from unittest.mock import patch

import comtypes

import input_control
import volume_control


class FakeVoice:
    def __init__(self):
        self.spoken = []

    def speak(self, text):
        self.spoken.append(text)


# ---------------------------------------------------------------------
# Relative volume up/down - unchanged since Phase 3 (multimedia keys)
# ---------------------------------------------------------------------

def test_volume_up():
    voice = FakeVoice()

    with patch("volume_control.input_control.press_key") as mock_press:
        handled = volume_control.handle("volume up", voice)

    assert handled is True
    mock_press.assert_called_once_with(input_control.VK_VOLUME_UP)


def test_volume_down():
    voice = FakeVoice()

    with patch("volume_control.input_control.press_key") as mock_press:
        handled = volume_control.handle("volume down", voice)

    assert handled is True
    mock_press.assert_called_once_with(input_control.VK_VOLUME_DOWN)


# ---------------------------------------------------------------------
# PHASE 7: true mute/unmute via Core Audio - idempotent, not a toggle.
# Replaces the old VK_VOLUME_MUTE toggle-key behavior.
# ---------------------------------------------------------------------

def test_mute_calls_true_set_mute():
    voice = FakeVoice()

    with patch("volume_control.audio_endpoint.set_mute") as mock_set_mute, \
         patch("volume_control.input_control.press_key") as mock_press:
        handled = volume_control.handle("mute", voice)

    assert handled is True
    mock_set_mute.assert_called_once_with(True)
    mock_press.assert_not_called()


def test_unmute_calls_true_set_mute_false():
    voice = FakeVoice()

    with patch("volume_control.audio_endpoint.set_mute") as mock_set_mute, \
         patch("volume_control.input_control.press_key") as mock_press:
        handled = volume_control.handle("unmute", voice)

    assert handled is True
    mock_set_mute.assert_called_once_with(False)
    mock_press.assert_not_called()


def test_unmute_does_not_also_trigger_mute_branch():
    """Regression guard: 'unmute' contains 'mute' as a substring, so the
    handler must check 'unmute' first or this would double-handle."""
    voice = FakeVoice()

    with patch("volume_control.audio_endpoint.set_mute") as mock_set_mute:
        handled = volume_control.handle("unmute", voice)

    assert handled is True
    assert mock_set_mute.call_count == 1
    mock_set_mute.assert_called_once_with(False)


def test_mute_is_idempotent_regardless_of_prior_state():
    """Unlike the old toggle behavior, calling mute() repeatedly must
    always request the muted state, never flip back to unmuted."""
    voice = FakeVoice()

    with patch("volume_control.audio_endpoint.set_mute") as mock_set_mute:
        volume_control.mute(voice)
        volume_control.mute(voice)

    assert mock_set_mute.call_args_list == [((True,),), ((True,),)]


def test_unmute_is_idempotent_regardless_of_prior_state():
    voice = FakeVoice()

    with patch("volume_control.audio_endpoint.set_mute") as mock_set_mute:
        volume_control.unmute(voice)
        volume_control.unmute(voice)

    assert mock_set_mute.call_args_list == [((False,),), ((False,),)]


def test_mute_speaks_confirmation():
    voice = FakeVoice()

    with patch("volume_control.audio_endpoint.set_mute"):
        volume_control.mute(voice)

    assert "Muting" in voice.spoken[-1]


def test_unmute_speaks_confirmation():
    voice = FakeVoice()

    with patch("volume_control.audio_endpoint.set_mute"):
        volume_control.unmute(voice)

    assert "Unmuting" in voice.spoken[-1]


def test_mute_com_error_is_handled_gracefully():
    """A real-world Core Audio failure (e.g. no default playback
    device) must not crash JARVIS."""
    voice = FakeVoice()

    with patch(
        "volume_control.audio_endpoint.set_mute",
        side_effect=comtypes.COMError(-2147023728, "text", ("details",)),
    ):
        volume_control.mute(voice)

    assert "couldn't mute" in voice.spoken[-1]


def test_unmute_os_error_is_handled_gracefully():
    voice = FakeVoice()

    with patch(
        "volume_control.audio_endpoint.set_mute",
        side_effect=OSError("no default audio device"),
    ):
        volume_control.unmute(voice)

    assert "couldn't unmute" in voice.spoken[-1]


# ---------------------------------------------------------------------
# PHASE 7: absolute volume ("set volume to <N>") via Core Audio.
# ---------------------------------------------------------------------

def test_set_volume_routes_to_core_audio_wrapper():
    voice = FakeVoice()

    with patch("volume_control.audio_endpoint.set_volume_percent") as mock_set:
        handled = volume_control.handle("set volume to 40", voice)

    assert handled is True
    mock_set.assert_called_once_with(40)


def test_set_volume_0_percent():
    voice = FakeVoice()

    with patch("volume_control.audio_endpoint.set_volume_percent") as mock_set:
        volume_control.set_volume(voice, 0)

    mock_set.assert_called_once_with(0)


def test_set_volume_100_percent():
    voice = FakeVoice()

    with patch("volume_control.audio_endpoint.set_volume_percent") as mock_set:
        volume_control.set_volume(voice, 100)

    mock_set.assert_called_once_with(100)


def test_set_volume_speaks_confirmation():
    voice = FakeVoice()

    with patch("volume_control.audio_endpoint.set_volume_percent"):
        volume_control.set_volume(voice, 40)

    assert "40 percent" in voice.spoken[-1]


def test_set_volume_rejects_value_above_100_without_calling_core_audio():
    """Defense in depth: even if set_volume() were somehow called
    directly with an out-of-range value (bypassing command_parser's own
    validation), it must still refuse to call the COM layer."""
    voice = FakeVoice()

    with patch("volume_control.audio_endpoint.set_volume_percent") as mock_set:
        volume_control.set_volume(voice, 150)

    mock_set.assert_not_called()
    assert "between 0 and 100" in voice.spoken[-1]


def test_set_volume_rejects_negative_value_without_calling_core_audio():
    voice = FakeVoice()

    with patch("volume_control.audio_endpoint.set_volume_percent") as mock_set:
        volume_control.set_volume(voice, -10)

    mock_set.assert_not_called()
    assert "between 0 and 100" in voice.spoken[-1]


def test_set_volume_com_error_is_handled_gracefully():
    voice = FakeVoice()

    with patch(
        "volume_control.audio_endpoint.set_volume_percent",
        side_effect=comtypes.COMError(-2147023728, "text", ("details",)),
    ):
        volume_control.set_volume(voice, 40)

    assert "couldn't change the volume" in voice.spoken[-1]


# ---------------------------------------------------------------------
def test_no_match_returns_false():
    voice = FakeVoice()

    handled = volume_control.handle("open notepad", voice)

    assert handled is False
    assert voice.spoken == []
