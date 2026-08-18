from unittest.mock import patch

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
