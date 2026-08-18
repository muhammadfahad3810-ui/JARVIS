from unittest.mock import patch

import mouse_control


class FakeVoice:
    def __init__(self):
        self.spoken = []

    def speak(self, text):
        self.spoken.append(text)


def test_click():
    voice = FakeVoice()

    with patch("mouse_control.input_control.click_mouse") as mock_click:
        handled = mouse_control.handle("click", voice)

    assert handled is True
    mock_click.assert_called_once_with()
    assert voice.spoken == ["Clicking."]


def test_left_click_triggers_plain_click():
    voice = FakeVoice()

    with patch("mouse_control.input_control.click_mouse") as mock_click:
        handled = mouse_control.handle("left click", voice)

    assert handled is True
    mock_click.assert_called_once_with()


def test_double_click():
    voice = FakeVoice()

    with patch("mouse_control.input_control.click_mouse") as mock_click:
        handled = mouse_control.handle("double click", voice)

    assert handled is True
    assert mock_click.call_count == 2
    assert voice.spoken == ["Double clicking."]


def test_double_click_not_swallowed_by_bare_click_check():
    """"double click" contains "click" as a substring - the more
    specific check must win, and must never also trigger a plain
    click or a right click."""
    voice = FakeVoice()

    with patch("mouse_control.input_control.click_mouse") as mock_click, \
         patch("mouse_control.input_control.right_click_mouse") as mock_right:
        mouse_control.handle("double click", voice)

    mock_right.assert_not_called()
    assert mock_click.call_count == 2


def test_right_click():
    voice = FakeVoice()

    with patch("mouse_control.input_control.right_click_mouse") as mock_right:
        handled = mouse_control.handle("right click", voice)

    assert handled is True
    mock_right.assert_called_once_with()
    assert voice.spoken == ["Right clicking."]


def test_right_click_not_swallowed_by_bare_click_check():
    voice = FakeVoice()

    with patch("mouse_control.input_control.click_mouse") as mock_click, \
         patch("mouse_control.input_control.right_click_mouse") as mock_right:
        mouse_control.handle("right click", voice)

    mock_click.assert_not_called()
    mock_right.assert_called_once_with()


def test_move_left():
    voice = FakeVoice()

    with patch("mouse_control.input_control.move_mouse_by") as mock_move:
        handled = mouse_control.handle("move left", voice)

    assert handled is True
    mock_move.assert_called_once_with(-mouse_control.MOVE_STEP_PIXELS, 0)
    assert voice.spoken == ["Moving left."]


def test_move_right():
    voice = FakeVoice()

    with patch("mouse_control.input_control.move_mouse_by") as mock_move:
        handled = mouse_control.handle("move right", voice)

    assert handled is True
    mock_move.assert_called_once_with(mouse_control.MOVE_STEP_PIXELS, 0)


def test_move_up():
    voice = FakeVoice()

    with patch("mouse_control.input_control.move_mouse_by") as mock_move:
        handled = mouse_control.handle("move up", voice)

    assert handled is True
    mock_move.assert_called_once_with(0, -mouse_control.MOVE_STEP_PIXELS)


def test_move_down():
    voice = FakeVoice()

    with patch("mouse_control.input_control.move_mouse_by") as mock_move:
        handled = mouse_control.handle("move down", voice)

    assert handled is True
    mock_move.assert_called_once_with(0, mouse_control.MOVE_STEP_PIXELS)


def test_no_match_returns_false():
    voice = FakeVoice()

    handled = mouse_control.handle("open notepad", voice)

    assert handled is False
    assert voice.spoken == []
