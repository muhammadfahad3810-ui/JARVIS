from unittest.mock import patch

import input_control
import keyboard_control


class FakeVoice:
    def __init__(self):
        self.spoken = []

    def speak(self, text):
        self.spoken.append(text)


def test_press_enter():
    voice = FakeVoice()

    with patch("keyboard_control.input_control.press_key") as mock_press:
        handled = keyboard_control.handle("press enter", voice)

    assert handled is True
    mock_press.assert_called_once_with(input_control.VK_RETURN)


def test_press_escape():
    voice = FakeVoice()

    with patch("keyboard_control.input_control.press_key") as mock_press:
        handled = keyboard_control.handle("press escape", voice)

    assert handled is True
    mock_press.assert_called_once_with(input_control.VK_ESCAPE)


def test_press_space():
    voice = FakeVoice()

    with patch("keyboard_control.input_control.press_key") as mock_press:
        handled = keyboard_control.handle("press space", voice)

    assert handled is True
    mock_press.assert_called_once_with(input_control.VK_SPACE)


def test_press_tab():
    voice = FakeVoice()

    with patch("keyboard_control.input_control.press_key") as mock_press:
        handled = keyboard_control.handle("press tab", voice)

    assert handled is True
    mock_press.assert_called_once_with(input_control.VK_TAB)


def test_copy():
    voice = FakeVoice()

    with patch("keyboard_control.input_control.press_key_combo") as mock_combo:
        handled = keyboard_control.handle("copy", voice)

    assert handled is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_C
    )


def test_paste():
    voice = FakeVoice()

    with patch("keyboard_control.input_control.press_key_combo") as mock_combo:
        handled = keyboard_control.handle("paste", voice)

    assert handled is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_V
    )


def test_select_all():
    voice = FakeVoice()

    with patch("keyboard_control.input_control.press_key_combo") as mock_combo:
        handled = keyboard_control.handle("select all", voice)

    assert handled is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_A
    )


def test_undo():
    voice = FakeVoice()

    with patch("keyboard_control.input_control.press_key_combo") as mock_combo:
        handled = keyboard_control.handle("undo", voice)

    assert handled is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_Z
    )


def test_no_match_returns_false():
    voice = FakeVoice()

    handled = keyboard_control.handle("open notepad", voice)

    assert handled is False
    assert voice.spoken == []
