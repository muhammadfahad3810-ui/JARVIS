from unittest.mock import patch

import input_control
import media_control


class FakeVoice:
    def __init__(self):
        self.spoken = []

    def speak(self, text):
        self.spoken.append(text)


def test_play_pause():
    voice = FakeVoice()

    with patch("media_control.input_control.press_key") as mock_press:
        handled = media_control.handle("play", voice)

    assert handled is True
    mock_press.assert_called_once_with(input_control.VK_MEDIA_PLAY_PAUSE)


def test_pause():
    voice = FakeVoice()

    with patch("media_control.input_control.press_key") as mock_press:
        handled = media_control.handle("pause", voice)

    assert handled is True
    mock_press.assert_called_once_with(input_control.VK_MEDIA_PLAY_PAUSE)


def test_next_track():
    voice = FakeVoice()

    with patch("media_control.input_control.press_key") as mock_press:
        handled = media_control.handle("next track", voice)

    assert handled is True
    mock_press.assert_called_once_with(input_control.VK_MEDIA_NEXT_TRACK)


def test_previous_track():
    voice = FakeVoice()

    with patch("media_control.input_control.press_key") as mock_press:
        handled = media_control.handle("previous track", voice)

    assert handled is True
    mock_press.assert_called_once_with(input_control.VK_MEDIA_PREV_TRACK)


def test_no_match_returns_false():
    voice = FakeVoice()

    handled = media_control.handle("open notepad", voice)

    assert handled is False
    assert voice.spoken == []
