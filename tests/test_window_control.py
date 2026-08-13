from unittest.mock import patch

import input_control
import window_control


class FakeVoice:
    def __init__(self):
        self.spoken = []

    def speak(self, text):
        self.spoken.append(text)


def test_minimize_window():
    voice = FakeVoice()

    with patch("window_control.user32.GetForegroundWindow", return_value=123), \
         patch("window_control.user32.ShowWindow") as mock_show:
        handled = window_control.handle("minimize this window", voice)

    assert handled is True
    mock_show.assert_called_once_with(123, window_control.SW_MINIMIZE)


def test_maximize_window():
    voice = FakeVoice()

    with patch("window_control.user32.GetForegroundWindow", return_value=123), \
         patch("window_control.user32.ShowWindow") as mock_show:
        handled = window_control.handle("maximize current window", voice)

    assert handled is True
    mock_show.assert_called_once_with(123, window_control.SW_MAXIMIZE)


def test_restore_window():
    voice = FakeVoice()

    with patch("window_control.user32.GetForegroundWindow", return_value=123), \
         patch("window_control.user32.ShowWindow") as mock_show:
        handled = window_control.handle("restore window", voice)

    assert handled is True
    mock_show.assert_called_once_with(123, window_control.SW_RESTORE)


def test_close_window():
    voice = FakeVoice()

    with patch("window_control.user32.GetForegroundWindow", return_value=123), \
         patch("window_control.user32.PostMessageW") as mock_post:
        handled = window_control.handle("close this window", voice)

    assert handled is True
    mock_post.assert_called_once_with(123, window_control.WM_CLOSE, 0, 0)


def test_switch_window():
    voice = FakeVoice()

    with patch("window_control.input_control.press_key_combo") as mock_combo:
        handled = window_control.handle("switch window", voice)

    assert handled is True
    mock_combo.assert_called_once_with(
        input_control.VK_MENU, input_control.VK_TAB
    )


def test_switch_to_next_window():
    voice = FakeVoice()

    with patch("window_control.input_control.press_key_combo") as mock_combo:
        handled = window_control.handle("switch to next window", voice)

    assert handled is True
    mock_combo.assert_called_once_with(
        input_control.VK_MENU, input_control.VK_TAB
    )


def test_show_desktop():
    voice = FakeVoice()

    with patch("window_control.input_control.press_key_combo") as mock_combo:
        handled = window_control.handle("show desktop", voice)

    assert handled is True
    mock_combo.assert_called_once_with(
        input_control.VK_LWIN, input_control.VK_KEY_D
    )


def test_no_foreground_window_does_not_crash():
    voice = FakeVoice()

    with patch("window_control.user32.GetForegroundWindow", return_value=0), \
         patch("window_control.user32.ShowWindow") as mock_show:
        handled = window_control.handle("minimize this window", voice)

    assert handled is True
    mock_show.assert_not_called()


def test_no_match_returns_false():
    voice = FakeVoice()

    handled = window_control.handle("open notepad", voice)

    assert handled is False
    assert voice.spoken == []


# ---------------------------------------------------------------------
# PHASE 6: low-level window enumeration plumbing
# ---------------------------------------------------------------------

def test_list_visible_window_titles_skips_hidden_and_empty_titled_windows():
    def fake_enum_windows(callback, _lparam):
        callback(111, 0)
        callback(222, 0)
        callback(333, 0)
        return True

    def fake_is_visible(hwnd):
        return hwnd != 222  # 222 is hidden

    def fake_get_length(hwnd):
        return {111: len("Untitled - Notepad"), 333: 0}.get(hwnd, 0)

    def fake_get_text(hwnd, buffer, _size):
        if hwnd == 111:
            buffer.value = "Untitled - Notepad"
        return 0

    with patch("window_control.user32.EnumWindows", side_effect=fake_enum_windows), \
         patch("window_control.user32.IsWindowVisible", side_effect=fake_is_visible), \
         patch("window_control.user32.GetWindowTextLengthW", side_effect=fake_get_length), \
         patch("window_control.user32.GetWindowTextW", side_effect=fake_get_text):
        result = window_control._list_visible_window_titles()

    assert result == [(111, "Untitled - Notepad")]


# ---------------------------------------------------------------------
# PHASE 6: target resolution - allow-list is the only way in
# ---------------------------------------------------------------------

def test_find_window_by_application_found():
    with patch(
        "window_control._list_visible_window_titles",
        return_value=[(1, "Task Manager"), (2, "New Tab - Google Chrome")],
    ):
        hwnd = window_control.find_window_by_application("chrome")

    assert hwnd == 2


def test_find_window_by_application_not_found():
    with patch(
        "window_control._list_visible_window_titles",
        return_value=[(1, "Task Manager")],
    ):
        hwnd = window_control.find_window_by_application("chrome")

    assert hwnd is None


def test_find_window_by_application_first_match_wins():
    """Documented behavior: if multiple windows match, the first one
    found during enumeration is used."""
    with patch(
        "window_control._list_visible_window_titles",
        return_value=[
            (10, "Tab A - Google Chrome"),
            (20, "Tab B - Google Chrome"),
        ],
    ):
        hwnd = window_control.find_window_by_application("chrome")

    assert hwnd == 10


def test_resolve_window_target_known_app_found():
    with patch(
        "window_control.find_window_by_application", return_value=42
    ):
        is_known, hwnd = window_control.resolve_window_target("chrome")

    assert is_known is True
    assert hwnd == 42


def test_resolve_window_target_known_app_not_found():
    with patch(
        "window_control.find_window_by_application", return_value=None
    ):
        is_known, hwnd = window_control.resolve_window_target("chrome")

    assert is_known is True
    assert hwnd is None


def test_resolve_window_target_unknown_app_never_enumerates():
    with patch(
        "window_control._list_visible_window_titles"
    ) as mock_list:
        is_known, hwnd = window_control.resolve_window_target("spotify")

    assert is_known is False
    assert hwnd is None
    mock_list.assert_not_called()


# ---------------------------------------------------------------------
# PHASE 6: by-name action functions
# ---------------------------------------------------------------------

def test_minimize_window_by_name_found():
    voice = FakeVoice()

    with patch(
        "window_control.resolve_window_target", return_value=(True, 55)
    ), patch("window_control.user32.ShowWindow") as mock_show:
        window_control.minimize_window_by_name("chrome", voice)

    mock_show.assert_called_once_with(55, window_control.SW_MINIMIZE)


def test_minimize_window_by_name_not_found_speaks_and_does_nothing():
    voice = FakeVoice()

    with patch(
        "window_control.resolve_window_target", return_value=(True, None)
    ), patch("window_control.user32.ShowWindow") as mock_show:
        window_control.minimize_window_by_name("chrome", voice)

    mock_show.assert_not_called()
    assert "couldn't find an open Chrome window" in voice.spoken[-1]


def test_maximize_window_by_name_found():
    voice = FakeVoice()

    with patch(
        "window_control.resolve_window_target", return_value=(True, 55)
    ), patch("window_control.user32.ShowWindow") as mock_show:
        window_control.maximize_window_by_name("chrome", voice)

    mock_show.assert_called_once_with(55, window_control.SW_MAXIMIZE)


def test_restore_window_by_name_found():
    voice = FakeVoice()

    with patch(
        "window_control.resolve_window_target", return_value=(True, 55)
    ), patch("window_control.user32.ShowWindow") as mock_show:
        window_control.restore_window_by_name("chrome", voice)

    mock_show.assert_called_once_with(55, window_control.SW_RESTORE)


def test_close_window_by_name_found_uses_postmessage():
    voice = FakeVoice()

    with patch(
        "window_control.resolve_window_target", return_value=(True, 55)
    ), patch("window_control.user32.PostMessageW") as mock_post:
        window_control.close_window_by_name("chrome", voice)

    mock_post.assert_called_once_with(55, window_control.WM_CLOSE, 0, 0)


def test_switch_to_window_by_name_found_restores_and_activates():
    voice = FakeVoice()

    with patch(
        "window_control.resolve_window_target", return_value=(True, 55)
    ), patch("window_control.user32.ShowWindow") as mock_show, \
         patch("window_control.user32.SetForegroundWindow") as mock_setfg:
        window_control.switch_to_window_by_name("notepad", voice)

    mock_show.assert_called_once_with(55, window_control.SW_RESTORE)
    mock_setfg.assert_called_once_with(55)


def test_by_name_action_unknown_app_never_calls_windows_api():
    """Defense in depth: even if a by-name function were somehow called
    with an unknown app name directly, it must still refuse to act."""
    voice = FakeVoice()

    with patch(
        "window_control.resolve_window_target", return_value=(False, None)
    ), patch("window_control.user32.ShowWindow") as mock_show:
        window_control.minimize_window_by_name("spotify", voice)

    mock_show.assert_not_called()
    assert "don't know an application called" in voice.spoken[-1]


# ---------------------------------------------------------------------
# PHASE 6: handle_targeted() routing
# ---------------------------------------------------------------------

def test_handle_targeted_minimize_chrome():
    voice = FakeVoice()

    with patch(
        "window_control.resolve_window_target", return_value=(True, 1)
    ), patch("window_control.user32.ShowWindow") as mock_show:
        handled = window_control.handle_targeted("minimize chrome", voice)

    assert handled is True
    mock_show.assert_called_once_with(1, window_control.SW_MINIMIZE)


def test_handle_targeted_switch_to_notepad():
    voice = FakeVoice()

    with patch(
        "window_control.resolve_window_target", return_value=(True, 1)
    ), patch("window_control.user32.ShowWindow"), \
         patch("window_control.user32.SetForegroundWindow") as mock_setfg:
        handled = window_control.handle_targeted("switch to notepad", voice)

    assert handled is True
    mock_setfg.assert_called_once_with(1)


def test_handle_targeted_close_the_notepad_window_phrase():
    voice = FakeVoice()

    with patch(
        "window_control.resolve_window_target", return_value=(True, 1)
    ), patch("window_control.user32.PostMessageW") as mock_post:
        handled = window_control.handle_targeted(
            "close the notepad window", voice
        )

    assert handled is True
    mock_post.assert_called_once_with(
        1, window_control.WM_CLOSE, 0, 0
    )


def test_handle_targeted_unknown_app_returns_false_no_enumeration():
    voice = FakeVoice()

    with patch(
        "window_control._list_visible_window_titles"
    ) as mock_list:
        handled = window_control.handle_targeted("close spotify", voice)

    assert handled is False
    mock_list.assert_not_called()
    assert voice.spoken == []


def test_handle_targeted_no_app_name_returns_false():
    voice = FakeVoice()

    handled = window_control.handle_targeted("minimize this window", voice)

    assert handled is False
    assert voice.spoken == []


def test_handle_targeted_app_name_without_action_verb_returns_false():
    """'open chrome' contains 'chrome' but no minimize/maximize/restore/
    close/switch verb - must not be intercepted; web_control should
    still get a chance to handle it as an OPEN command."""
    voice = FakeVoice()

    handled = window_control.handle_targeted("open chrome", voice)

    assert handled is False
    assert voice.spoken == []
