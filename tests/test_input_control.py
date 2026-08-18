import ctypes
from unittest.mock import patch

import input_control


# ---------------------------------------------------------------------
# SendInput struct size - load-bearing, not decorative: SendInput
# silently rejects (returns 0, injects nothing) the whole call if the
# cbSize argument doesn't match its own fixed idea of sizeof(INPUT).
# Pins the real, ABI-correct size so a future edit to the ctypes
# structures can't silently reintroduce that bug.
# ---------------------------------------------------------------------

def test_input_struct_size_matches_real_win32_input_struct():
    expected = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
    assert ctypes.sizeof(input_control._INPUT) == expected


# ---------------------------------------------------------------------
# press_key() / press_key_combo() - success/failure propagation
# ---------------------------------------------------------------------

def test_press_key_sends_one_down_and_one_up_event():
    with patch("input_control.user32.SendInput", return_value=1) as mock_send:
        result = input_control.press_key(input_control.VK_RETURN)

    assert result is True
    assert mock_send.call_count == 2


def test_press_key_returns_false_when_sendinput_rejects_event():
    """The exact scenario this fix targets: a blocked/rejected
    injection must be reported as failure, not silently treated as
    success."""
    with patch("input_control.user32.SendInput", return_value=0):
        result = input_control.press_key(input_control.VK_RETURN)

    assert result is False


def test_press_key_returns_false_if_only_key_up_is_rejected():
    with patch("input_control.user32.SendInput", side_effect=[1, 0]):
        result = input_control.press_key(input_control.VK_RETURN)

    assert result is False


def test_press_key_combo_sends_down_and_up_for_every_key():
    with patch("input_control.user32.SendInput", return_value=1) as mock_send:
        result = input_control.press_key_combo(
            input_control.VK_CONTROL, input_control.VK_KEY_T
        )

    assert result is True
    assert mock_send.call_count == 4  # 2 keys x (1 down + 1 up)


def test_press_key_combo_returns_false_if_any_event_rejected():
    with patch("input_control.user32.SendInput", side_effect=[1, 0, 1, 1]):
        result = input_control.press_key_combo(
            input_control.VK_CONTROL, input_control.VK_KEY_T
        )

    assert result is False


def test_press_key_combo_three_keys_sends_six_events():
    with patch("input_control.user32.SendInput", return_value=1) as mock_send:
        result = input_control.press_key_combo(
            input_control.VK_CONTROL, input_control.VK_SHIFT, input_control.VK_ESCAPE
        )

    assert result is True
    assert mock_send.call_count == 6


# ---------------------------------------------------------------------
# Extended-key flagging (arrow/paging keys need KEYEVENTF_EXTENDEDKEY)
# ---------------------------------------------------------------------

def _captured_flags(vk_code):
    """Call press_key(vk_code) with a mocked SendInput and return the
    dwFlags value from every INPUT structure it was called with, in
    order (down, then up)."""

    with patch("input_control.user32.SendInput", return_value=1) as mock_send:
        input_control.press_key(vk_code)

    return [
        call.args[1].contents.union.ki.dwFlags
        for call in mock_send.call_args_list
    ]


def test_extended_flag_set_for_left_arrow():
    flags = _captured_flags(input_control.VK_LEFT)
    assert all(f & input_control.KEYEVENTF_EXTENDEDKEY for f in flags)


def test_extended_flag_set_for_right_arrow():
    flags = _captured_flags(input_control.VK_RIGHT)
    assert all(f & input_control.KEYEVENTF_EXTENDEDKEY for f in flags)


def test_extended_flag_set_for_page_up_and_page_down():
    assert all(
        f & input_control.KEYEVENTF_EXTENDEDKEY
        for f in _captured_flags(input_control.VK_PRIOR)
    )
    assert all(
        f & input_control.KEYEVENTF_EXTENDEDKEY
        for f in _captured_flags(input_control.VK_NEXT)
    )


def test_extended_flag_not_set_for_letter_keys():
    flags = _captured_flags(input_control.VK_KEY_T)
    assert not any(f & input_control.KEYEVENTF_EXTENDEDKEY for f in flags)


def test_extended_flag_not_set_for_enter():
    flags = _captured_flags(input_control.VK_RETURN)
    assert not any(f & input_control.KEYEVENTF_EXTENDEDKEY for f in flags)


def test_key_up_flag_set_only_on_the_release_event():
    with patch("input_control.user32.SendInput", return_value=1) as mock_send:
        input_control.press_key(input_control.VK_RETURN)

    down_flags = mock_send.call_args_list[0].args[1].contents.union.ki.dwFlags
    up_flags = mock_send.call_args_list[1].args[1].contents.union.ki.dwFlags

    assert not (down_flags & input_control.KEYEVENTF_KEYUP)
    assert up_flags & input_control.KEYEVENTF_KEYUP


# ---------------------------------------------------------------------
# Mouse (unchanged mechanism - regression coverage only)
# ---------------------------------------------------------------------

def test_click_mouse_presses_and_releases_left_button():
    with patch("input_control.user32.mouse_event") as mock_event:
        input_control.click_mouse()

    assert mock_event.call_args_list[0].args[0] == input_control.MOUSEEVENTF_LEFTDOWN
    assert mock_event.call_args_list[1].args[0] == input_control.MOUSEEVENTF_LEFTUP


def test_right_click_mouse_presses_and_releases_right_button():
    with patch("input_control.user32.mouse_event") as mock_event:
        input_control.right_click_mouse()

    assert mock_event.call_args_list[0].args[0] == input_control.MOUSEEVENTF_RIGHTDOWN
    assert mock_event.call_args_list[1].args[0] == input_control.MOUSEEVENTF_RIGHTUP


def test_move_mouse_by_offsets_current_position():
    with patch("input_control.get_cursor_pos", return_value=(100, 200)), \
         patch("input_control.user32.SetCursorPos") as mock_set:
        input_control.move_mouse_by(10, -5)

    mock_set.assert_called_once_with(110, 195)
