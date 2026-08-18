from unittest.mock import patch

import config
import input_control
import web_control


class FakeVoice:
    def __init__(self):
        self.spoken = []

    def speak(self, text):
        self.spoken.append(text)


# ---------------------------------------------------------------------
# Each browser action sends the correct keyboard sequence through the
# existing input_control abstraction - never a hardcoded Chrome path,
# never a second browser instance, never a browser-specific API. All
# of these operate on whatever window currently has focus (input_
# control.press_key/press_key_combo's own documented behavior).
# ---------------------------------------------------------------------

def test_new_tab_sends_ctrl_t():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=True) as mock_combo:
        web_control.new_tab(voice)

    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_T
    )
    assert voice.spoken == ["Opening new tab."]


def test_close_tab_sends_ctrl_w():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=True) as mock_combo:
        web_control.close_tab(voice)

    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_W
    )
    assert voice.spoken == ["Closing tab."]


# ---------------------------------------------------------------------
# Phase 11.11 follow-up: CLOSE_TAB live-action investigation.
#
# These go through the REAL, unmocked input_control.press_key_combo()
# (only the actual OS boundary - user32.SendInput - is mocked), so they
# prove the literal event sequence close_tab() causes to be injected:
# Ctrl-down, W-down, W-up, Ctrl-up, in that exact order, with the
# correct VK codes and KEYEVENTF_KEYUP flags on the right events - not
# just that "press_key_combo was called with some arguments". The
# new_tab() version alongside it is a direct, mechanical proof that
# close_tab() and new_tab() go through byte-identical machinery (same
# function, same call shape, same event ordering) - the only
# difference is which second VK code is pressed. If NEW_TAB visibly
# works against real Chrome and CLOSE_TAB does not, this test result
# rules out a code-level difference between the two as the cause.
# ---------------------------------------------------------------------

def _vk_and_up_flag(send_input_call):
    """Extract (wVk, key_up) from one recorded user32.SendInput() call
    - `call.args[1]` is the ctypes pointer to the INPUT struct that was
    actually passed."""

    ki = send_input_call.args[1].contents.union.ki
    return ki.wVk, bool(ki.dwFlags & input_control.KEYEVENTF_KEYUP)


def test_close_tab_sends_exact_ctrl_w_event_sequence_via_real_sendinput():
    voice = FakeVoice()

    with patch("input_control.user32.SendInput", return_value=1) as mock_send:
        web_control.close_tab(voice)

    assert [_vk_and_up_flag(c) for c in mock_send.call_args_list] == [
        (input_control.VK_CONTROL, False),  # Ctrl down
        (input_control.VK_KEY_W, False),    # W down
        (input_control.VK_KEY_W, True),     # W up
        (input_control.VK_CONTROL, True),   # Ctrl up
    ]
    assert voice.spoken == ["Closing tab."]


def test_new_tab_sends_exact_ctrl_t_event_sequence_via_real_sendinput():
    """Direct side-by-side comparison with the CLOSE_TAB test above -
    proves the two actions are mechanically identical apart from the
    VK code of the second key."""
    voice = FakeVoice()

    with patch("input_control.user32.SendInput", return_value=1) as mock_send:
        web_control.new_tab(voice)

    assert [_vk_and_up_flag(c) for c in mock_send.call_args_list] == [
        (input_control.VK_CONTROL, False),  # Ctrl down
        (input_control.VK_KEY_T, False),    # T down
        (input_control.VK_KEY_T, True),     # T up
        (input_control.VK_CONTROL, True),   # Ctrl up
    ]
    assert voice.spoken == ["Opening new tab."]


def test_close_tab_debug_logging_is_off_by_default():
    """config.DEBUG defaults to False - the diagnostic foreground-
    window logging added for this investigation must never run (zero
    overhead, zero behavior change) unless explicitly enabled."""
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=True), \
         patch("web_control._debug_foreground_window") as mock_fg:
        web_control.close_tab(voice)

    mock_fg.assert_not_called()


def test_close_tab_debug_logging_prints_foreground_window_before_and_after(capsys):
    voice = FakeVoice()

    with patch.object(config, "DEBUG", True), \
         patch("web_control.input_control.press_key_combo", return_value=True), \
         patch(
             "web_control._debug_foreground_window",
             side_effect=[(111, "Terminal"), (222, "Google Chrome")],
         ):
        web_control.close_tab(voice)

    output = capsys.readouterr().out
    assert "close_tab" in output
    assert "CTRL+W" in output
    assert "hwnd=111" in output and "Terminal" in output
    assert "hwnd=222" in output and "Google Chrome" in output
    assert "ok=True" in output


def test_close_tab_reports_failure_if_any_single_event_is_rejected():
    """Verifies close_tab() genuinely checks press_key_combo()'s real
    result (which itself requires EVERY one of the 4 events to be
    accepted - see input_control.press_key_combo()) rather than
    assuming success from a single call. A rejection on just the FINAL
    event (Ctrl-up) must still flip the spoken result to failure."""
    voice = FakeVoice()

    with patch("input_control.user32.SendInput", side_effect=[1, 1, 1, 0]):
        web_control.close_tab(voice)

    assert voice.spoken == [web_control.INPUT_FAILURE_MESSAGE]


def test_next_tab_sends_ctrl_tab():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=True) as mock_combo:
        web_control.next_tab(voice)

    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_TAB
    )
    assert voice.spoken == ["Switching to the next tab."]


def test_previous_tab_sends_ctrl_shift_tab():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=True) as mock_combo:
        web_control.previous_tab(voice)

    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_SHIFT, input_control.VK_TAB
    )
    assert voice.spoken == ["Switching to the previous tab."]


def test_refresh_sends_f5():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key", return_value=True) as mock_press:
        web_control.refresh(voice)

    mock_press.assert_called_once_with(input_control.VK_F5)
    assert voice.spoken == ["Refreshing."]


def test_go_back_sends_alt_left():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=True) as mock_combo:
        web_control.go_back(voice)

    mock_combo.assert_called_once_with(
        input_control.VK_MENU, input_control.VK_LEFT
    )
    assert voice.spoken == ["Going back."]


def test_go_forward_sends_alt_right():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=True) as mock_combo:
        web_control.go_forward(voice)

    mock_combo.assert_called_once_with(
        input_control.VK_MENU, input_control.VK_RIGHT
    )
    assert voice.spoken == ["Going forward."]


# ---------------------------------------------------------------------
# Honest success/failure reporting: JARVIS must not claim success when
# the low-level input injection was rejected by the OS.
# ---------------------------------------------------------------------

def test_new_tab_reports_failure_when_injection_rejected():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=False):
        web_control.new_tab(voice)

    assert voice.spoken == [web_control.INPUT_FAILURE_MESSAGE]


def test_close_tab_reports_failure_when_injection_rejected():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=False):
        web_control.close_tab(voice)

    assert voice.spoken == [web_control.INPUT_FAILURE_MESSAGE]


def test_next_tab_reports_failure_when_injection_rejected():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=False):
        web_control.next_tab(voice)

    assert voice.spoken == [web_control.INPUT_FAILURE_MESSAGE]


def test_previous_tab_reports_failure_when_injection_rejected():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=False):
        web_control.previous_tab(voice)

    assert voice.spoken == [web_control.INPUT_FAILURE_MESSAGE]


def test_refresh_reports_failure_when_injection_rejected():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key", return_value=False):
        web_control.refresh(voice)

    assert voice.spoken == [web_control.INPUT_FAILURE_MESSAGE]


def test_go_back_reports_failure_when_injection_rejected():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=False):
        web_control.go_back(voice)

    assert voice.spoken == [web_control.INPUT_FAILURE_MESSAGE]


def test_go_forward_reports_failure_when_injection_rejected():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=False):
        web_control.go_forward(voice)

    assert voice.spoken == [web_control.INPUT_FAILURE_MESSAGE]


def test_new_tab_never_launches_a_second_chrome_process():
    """Structural guarantee: the tab-management actions must never
    touch subprocess.Popen/webbrowser.open (the mechanisms open_chrome()
    uses) - only the existing keyboard-input abstraction."""
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=True), \
         patch("web_control.subprocess.Popen") as mock_popen, \
         patch("web_control.webbrowser.open") as mock_open:
        web_control.new_tab(voice)

    mock_popen.assert_not_called()
    mock_open.assert_not_called()


# ---------------------------------------------------------------------
# handle() dispatch - end-to-end through the same handler process()
# reaches, using real (mocked-at-input_control-level) functions.
# ---------------------------------------------------------------------

def test_handle_new_tab():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=True) as mock_combo:
        handled = web_control.handle("new tab", voice)

    assert handled is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_T
    )


def test_handle_open_new_tab():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=True) as mock_combo:
        handled = web_control.handle("open new tab", voice)

    assert handled is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_T
    )


def test_handle_open_a_new_chrome_tab_is_new_tab_not_open_chrome():
    """The exact live-test regression: "open a new chrome tab" must
    become NEW_TAB, never fall through to the bare "chrome" open
    check."""
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=True) as mock_combo, \
         patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open") as mock_open, \
         patch("web_control.subprocess.Popen") as mock_popen:
        handled = web_control.handle("open a new chrome tab", voice)

    assert handled is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_T
    )
    mock_open.assert_not_called()
    mock_popen.assert_not_called()
    assert voice.spoken == ["Opening new tab."]


def test_handle_new_browser_tab_is_new_tab():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=True) as mock_combo:
        handled = web_control.handle("new browser tab", voice)

    assert handled is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_T
    )


def test_handle_new_edge_tab_is_new_tab():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=True) as mock_combo:
        handled = web_control.handle("new edge tab", voice)

    assert handled is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_T
    )


def test_handle_close_tab():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=True) as mock_combo:
        handled = web_control.handle("close tab", voice)

    assert handled is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_W
    )


# ---------------------------------------------------------------------
# Phase 11.12: CLOSE_TAB article tolerance + precedence over NEW_TAB.
# Live-test regressions: "close the tab" -> "Pressing Tab." and
# "close the new tab" -> "Opening new tab.".
# ---------------------------------------------------------------------

def test_handle_close_the_tab():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=True) as mock_combo:
        handled = web_control.handle("close the tab", voice)

    assert handled is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_W
    )
    assert voice.spoken == ["Closing tab."]


def test_handle_close_this_tab():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=True) as mock_combo:
        handled = web_control.handle("close this tab", voice)

    assert handled is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_W
    )


def test_handle_close_a_tab():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=True) as mock_combo:
        handled = web_control.handle("close a tab", voice)

    assert handled is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_W
    )


def test_handle_close_the_new_tab_is_close_tab_not_new_tab():
    """The exact live-test regression: "close the new tab" contains the
    literal substring "new tab" too, but the verb "close" makes the
    intent unambiguous and must win over NEW_TAB_ALIASES."""
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=True) as mock_combo:
        handled = web_control.handle("close the new tab", voice)

    assert handled is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_W
    )
    assert voice.spoken == ["Closing tab."]


def test_handle_close_this_new_tab_is_close_tab():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=True) as mock_combo:
        handled = web_control.handle("close this new tab", voice)

    assert handled is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_W
    )


# ---------------------------------------------------------------------
# Phase 11.12 (round 2): "closed tab" - a past-tense STT variant of
# "close tab" observed live falling through to the bare-Tab rescue.
# ---------------------------------------------------------------------

def test_handle_closed_tab_is_close_tab():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=True) as mock_combo:
        handled = web_control.handle("closed tab", voice)

    assert handled is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_W
    )
    assert voice.spoken == ["Closing tab."]


def test_handle_closed_the_tab_is_close_tab():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=True) as mock_combo:
        handled = web_control.handle("closed the tab", voice)

    assert handled is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_W
    )


def test_closed_tab_does_not_false_match_enclosed():
    """Word-boundary-anchored: "closed?" must not match as a mid-word
    fragment of an unrelated word like "enclosed"."""
    voice = FakeVoice()

    handled = web_control.handle("the enclosed tab is fine", voice)

    assert handled is False


def test_close_the_tab_never_touches_press_key():
    """Negative case: must never fall through to keyboard_control's
    "press tab" (this test only proves web_control.handle() itself
    never calls the single-key press path - see test_commands.py for
    the full end-to-end proof against keyboard_control)."""
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=True), \
         patch("web_control.input_control.press_key") as mock_press:
        web_control.handle("close the tab", voice)

    mock_press.assert_not_called()


def test_handle_next_tab():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=True) as mock_combo:
        handled = web_control.handle("next tab", voice)

    assert handled is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_TAB
    )


def test_handle_previous_tab():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=True) as mock_combo:
        handled = web_control.handle("previous tab", voice)

    assert handled is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_SHIFT, input_control.VK_TAB
    )


def test_handle_switch_to_next_tab():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=True) as mock_combo:
        handled = web_control.handle("switch to next tab", voice)

    assert handled is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_TAB
    )


def test_handle_switch_to_previous_tab():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=True) as mock_combo:
        handled = web_control.handle("switch to previous tab", voice)

    assert handled is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_SHIFT, input_control.VK_TAB
    )


def test_handle_refresh():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key", return_value=True) as mock_press:
        handled = web_control.handle("refresh", voice)

    assert handled is True
    mock_press.assert_called_once_with(input_control.VK_F5)


def test_handle_reload_also_refreshes():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key", return_value=True) as mock_press:
        handled = web_control.handle("reload", voice)

    assert handled is True
    mock_press.assert_called_once_with(input_control.VK_F5)


def test_handle_go_back():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=True) as mock_combo:
        handled = web_control.handle("go back", voice)

    assert handled is True
    mock_combo.assert_called_once_with(
        input_control.VK_MENU, input_control.VK_LEFT
    )


def test_handle_go_forward():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo", return_value=True) as mock_combo:
        handled = web_control.handle("go forward", voice)

    assert handled is True
    mock_combo.assert_called_once_with(
        input_control.VK_MENU, input_control.VK_RIGHT
    )


def test_handle_press_backspace_still_not_treated_as_go_back():
    voice = FakeVoice()

    with patch("web_control.input_control.press_key_combo") as mock_combo:
        handled = web_control.handle("press backspace", voice)

    assert handled is False
    mock_combo.assert_not_called()


def test_handle_chrome_unaffected():
    voice = FakeVoice()

    with patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open") as mock_open:
        handled = web_control.handle("open chrome", voice)

    assert handled is True
    mock_open.assert_called_once_with("https://www.google.com")
    assert voice.spoken == ["Opening Chrome."]
