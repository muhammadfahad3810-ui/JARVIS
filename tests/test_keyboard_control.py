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


def test_scroll_up():
    voice = FakeVoice()

    with patch("keyboard_control.input_control.press_key") as mock_press:
        handled = keyboard_control.handle("scroll up", voice)

    assert handled is True
    mock_press.assert_called_once_with(input_control.VK_PRIOR)


def test_scroll_down():
    voice = FakeVoice()

    with patch("keyboard_control.input_control.press_key") as mock_press:
        handled = keyboard_control.handle("scroll down", voice)

    assert handled is True
    mock_press.assert_called_once_with(input_control.VK_NEXT)


def test_no_match_returns_false():
    voice = FakeVoice()

    handled = keyboard_control.handle("open notepad", voice)

    assert handled is False
    assert voice.spoken == []


def test_press_backspace():
    voice = FakeVoice()

    with patch("keyboard_control.input_control.press_key") as mock_press:
        handled = keyboard_control.handle("press backspace", voice)

    assert handled is True
    mock_press.assert_called_once_with(input_control.VK_BACK)


def test_press_delete_is_deliberately_not_recognized():
    """Security decision, not an oversight - see this module's own
    handle() docstring and tests/test_security.py's test_press_
    unknown_key_is_not_sent_to_keyboard: an unconfirmed Delete keypress
    can destructively delete a selected file/text, so Delete is the one
    key this project never adds."""
    voice = FakeVoice()

    handled = keyboard_control.handle("press delete", voice)

    assert handled is False
    assert voice.spoken == []


def test_press_ctrl_c_triggers_copy():
    voice = FakeVoice()

    with patch("keyboard_control.input_control.press_key_combo") as mock_combo:
        handled = keyboard_control.handle("press ctrl c", voice)

    assert handled is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_C
    )
    assert voice.spoken == ["Copying."]


def test_press_ctrl_v_triggers_paste():
    voice = FakeVoice()

    with patch("keyboard_control.input_control.press_key_combo") as mock_combo:
        handled = keyboard_control.handle("press ctrl v", voice)

    assert handled is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_V
    )


def test_press_ctrl_x_triggers_cut():
    voice = FakeVoice()

    with patch("keyboard_control.input_control.press_key_combo") as mock_combo:
        handled = keyboard_control.handle("press ctrl x", voice)

    assert handled is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_X
    )
    assert voice.spoken == ["Cutting."]


def test_press_ctrl_a_triggers_select_all():
    voice = FakeVoice()

    with patch("keyboard_control.input_control.press_key_combo") as mock_combo:
        handled = keyboard_control.handle("press ctrl a", voice)

    assert handled is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_A
    )


def test_press_ctrl_z_triggers_undo():
    voice = FakeVoice()

    with patch("keyboard_control.input_control.press_key_combo") as mock_combo:
        handled = keyboard_control.handle("press ctrl z", voice)

    assert handled is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_Z
    )


def test_press_alt_tab():
    voice = FakeVoice()

    with patch("keyboard_control.input_control.press_key_combo") as mock_combo, \
         patch("keyboard_control.input_control.press_key") as mock_press:
        handled = keyboard_control.handle("press alt tab", voice)

    assert handled is True
    mock_press.assert_not_called()
    mock_combo.assert_called_once_with(
        input_control.VK_MENU, input_control.VK_TAB
    )


def test_press_ctrl_shift_escape():
    voice = FakeVoice()

    with patch("keyboard_control.input_control.press_key_combo") as mock_combo:
        handled = keyboard_control.handle("press ctrl shift escape", voice)

    assert handled is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_SHIFT, input_control.VK_ESCAPE
    )
