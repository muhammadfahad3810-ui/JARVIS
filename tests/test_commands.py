from unittest.mock import patch

import commands
import media_control
import volume_control
import keyboard_control


class FakeVoice:
    """Records spoken text instead of using pyttsx3, so tests need no audio device."""

    def __init__(self):
        self.spoken = []

    def speak(self, text):
        self.spoken.append(text)


def make_processor():
    voice = FakeVoice()
    return commands.CommandProcessor(voice), voice


def test_empty_command_does_nothing():
    processor, voice = make_processor()

    result = processor.process("")

    assert result is True
    assert voice.spoken == []


def test_exit_command_stops_running():
    processor, voice = make_processor()

    result = processor.process("exit")

    assert result is False
    assert "Goodbye" in voice.spoken[-1]


def test_quit_goodbye_and_go_offline_are_also_exit_commands():
    for phrase in ["quit", "goodbye", "go offline"]:
        processor, voice = make_processor()

        result = processor.process(phrase)

        assert result is False


def test_time_command():
    processor, voice = make_processor()

    result = processor.process("what time is it")

    assert result is True
    assert "current time" in voice.spoken[-1]


def test_date_command():
    processor, voice = make_processor()

    result = processor.process("what's the date")

    assert result is True
    assert "Today is" in voice.spoken[-1]


def test_greeting_command():
    processor, voice = make_processor()

    result = processor.process("hello")

    assert result is True
    assert "JARVIS" in voice.spoken[-1]


def test_bare_hi_is_a_greeting():
    processor, voice = make_processor()

    result = processor.process("hi")

    assert result is True
    assert "JARVIS" in voice.spoken[-1]


def test_word_containing_hi_is_not_falsely_treated_as_greeting():
    """'this', 'shipping', etc. contain 'hi' as a substring but are not
    greetings - word-boundary matching must not treat them as one."""
    processor, voice = make_processor()

    result = processor.process("this is a test")

    assert result is True
    assert "don't know how to do that" in voice.spoken[-1]


def test_open_youtube_command():
    processor, voice = make_processor()

    with patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("open youtube")

    assert result is True
    mock_open.assert_called_once_with("https://www.youtube.com")


def test_search_for_command():
    processor, voice = make_processor()

    with patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("search for python")

    assert result is True
    mock_open.assert_called_once_with(
        "https://www.google.com/search?q=python"
    )


def test_open_chrome_falls_back_to_browser_when_no_exe_found():
    processor, voice = make_processor()

    with patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("open chrome")

    assert result is True
    mock_open.assert_called_once_with("https://www.google.com")


def test_open_notepad_command():
    processor, voice = make_processor()

    with patch("system_control.subprocess.Popen") as mock_popen:
        result = processor.process("open notepad")

    assert result is True
    mock_popen.assert_called_once_with(["notepad.exe"], shell=False)


def test_open_calculator_command():
    processor, voice = make_processor()

    with patch("system_control.subprocess.Popen") as mock_popen:
        result = processor.process("open calculator")

    assert result is True
    mock_popen.assert_called_once_with(["calc.exe"], shell=False)


def test_open_file_explorer_command():
    processor, voice = make_processor()

    with patch("system_control.subprocess.Popen") as mock_popen:
        result = processor.process("open file explorer")

    assert result is True
    mock_popen.assert_called_once_with(["explorer.exe"], shell=False)


def test_unknown_command():
    processor, voice = make_processor()

    result = processor.process("do a backflip")

    assert result is True
    assert "don't know how to do that" in voice.spoken[-1]


def test_unknown_command_with_filler_words_is_still_unknown():
    processor, voice = make_processor()

    result = processor.process("can you do a backflip for me")

    assert result is True
    assert "don't know how to do that" in voice.spoken[-1]


# ---------------------------------------------------------------------
# Natural-language variations routed end-to-end through CommandProcessor
# ---------------------------------------------------------------------

def test_launch_youtube_opens_youtube():
    processor, voice = make_processor()

    with patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("launch youtube")

    assert result is True
    mock_open.assert_called_once_with("https://www.youtube.com")


def test_open_up_youtube_opens_youtube():
    processor, voice = make_processor()

    with patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("open up youtube")

    assert result is True
    mock_open.assert_called_once_with("https://www.youtube.com")


def test_go_to_youtube_opens_youtube():
    processor, voice = make_processor()

    with patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("go to youtube")

    assert result is True
    mock_open.assert_called_once_with("https://www.youtube.com")


def test_can_you_open_youtube_for_me_opens_youtube():
    processor, voice = make_processor()

    with patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("can you open youtube for me")

    assert result is True
    mock_open.assert_called_once_with("https://www.youtube.com")


def test_google_python_searches_for_python():
    processor, voice = make_processor()

    with patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("google python")

    assert result is True
    mock_open.assert_called_once_with(
        "https://www.google.com/search?q=python"
    )


def test_look_up_python_searches_for_python():
    processor, voice = make_processor()

    with patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("look up python")

    assert result is True
    mock_open.assert_called_once_with(
        "https://www.google.com/search?q=python"
    )


def test_find_information_about_python_searches_for_python():
    processor, voice = make_processor()

    with patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("find information about python")

    assert result is True
    mock_open.assert_called_once_with(
        "https://www.google.com/search?q=python"
    )


def test_search_the_web_for_python_searches_for_python():
    processor, voice = make_processor()

    with patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("search the web for python")

    assert result is True
    mock_open.assert_called_once_with(
        "https://www.google.com/search?q=python"
    )


def test_launch_chrome_opens_chrome():
    processor, voice = make_processor()

    with patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("launch chrome")

    assert result is True
    mock_open.assert_called_once_with("https://www.google.com")


def test_start_notepad_opens_notepad():
    processor, voice = make_processor()

    with patch("system_control.subprocess.Popen") as mock_popen:
        result = processor.process("start notepad")

    assert result is True
    mock_popen.assert_called_once_with(["notepad.exe"], shell=False)


def test_launch_file_explorer_opens_file_explorer():
    processor, voice = make_processor()

    with patch("system_control.subprocess.Popen") as mock_popen:
        result = processor.process("launch file explorer")

    assert result is True
    mock_popen.assert_called_once_with(["explorer.exe"], shell=False)


def test_what_day_is_it_gives_the_date():
    processor, voice = make_processor()

    result = processor.process("what day is it")

    assert result is True
    assert "Today is" in voice.spoken[-1]


def test_tell_me_the_time_gives_the_time():
    processor, voice = make_processor()

    result = processor.process("tell me the time")

    assert result is True
    assert "current time" in voice.spoken[-1]


def test_existing_lock_shutdown_restart_still_work_unchanged():
    processor, voice = make_processor()

    with patch("system_control.os.system") as mock_system:
        result = processor.process("lock computer")

    assert result is True
    mock_system.assert_called_once_with("rundll32.exe user32.dll,LockWorkStation")


def test_existing_shutdown_and_restart_still_work_unchanged():
    for phrase, expected_call in [
        ("shutdown computer", "shutdown /s /t 5"),
        ("restart computer", "shutdown /r /t 5"),
    ]:
        processor, voice = make_processor()

        with patch("system_control.os.system") as mock_system:
            result = processor.process(phrase)

        assert result is True
        mock_system.assert_called_once_with(expected_call)


# ---------------------------------------------------------------------
# PHASE 3: new application launching (Edge, PowerShell, "run" verb)
# ---------------------------------------------------------------------

def test_open_edge_command():
    processor, voice = make_processor()

    with patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("open edge")

    assert result is True
    mock_open.assert_called_once_with("https://www.bing.com")


def test_launch_powershell_command():
    processor, voice = make_processor()

    with patch("system_control.subprocess.Popen") as mock_popen:
        result = processor.process("launch powershell")

    assert result is True
    mock_popen.assert_called_once_with(["powershell.exe"], shell=False)


def test_run_notepad_command():
    processor, voice = make_processor()

    with patch("system_control.subprocess.Popen") as mock_popen:
        result = processor.process("run notepad")

    assert result is True
    mock_popen.assert_called_once_with(["notepad.exe"], shell=False)


# ---------------------------------------------------------------------
# PHASE 3: window control
# ---------------------------------------------------------------------

def test_minimize_this_window_command():
    processor, voice = make_processor()

    with patch("window_control.user32.GetForegroundWindow", return_value=1), \
         patch("window_control.user32.ShowWindow") as mock_show:
        result = processor.process("minimize this window")

    assert result is True
    mock_show.assert_called_once()


def test_minimize_this_window_is_not_misrouted_to_greeting():
    """Regression guard: bare substring greeting matching previously
    treated 'this' as containing the greeting word 'hi', which would
    have swallowed this command before it ever reached window control."""
    processor, voice = make_processor()

    with patch("window_control.user32.GetForegroundWindow", return_value=1), \
         patch("window_control.user32.ShowWindow"):
        processor.process("minimize this window")

    assert "JARVIS. How can I help you?" not in voice.spoken[-1]


def test_show_desktop_command():
    processor, voice = make_processor()

    with patch("window_control.input_control.press_key_combo") as mock_combo:
        result = processor.process("show desktop")

    assert result is True
    mock_combo.assert_called_once()


# ---------------------------------------------------------------------
# PHASE 3: volume control
# ---------------------------------------------------------------------

def test_increase_volume_command():
    processor, voice = make_processor()

    with patch("volume_control.input_control.press_key") as mock_press:
        result = processor.process("increase volume")

    assert result is True
    mock_press.assert_called_once_with(volume_control.input_control.VK_VOLUME_UP)


def test_mute_the_computer_command():
    """Phase 7: mute is now true Core Audio SetMute, not a multimedia
    key press - see test_volume_control.py for the dedicated Phase 7
    coverage of mute/unmute/set-volume."""

    processor, voice = make_processor()

    with patch("volume_control.audio_endpoint.set_mute") as mock_set_mute:
        result = processor.process("mute the computer")

    assert result is True
    mock_set_mute.assert_called_once_with(True)


# ---------------------------------------------------------------------
# PHASE 7: absolute volume control (end-to-end dispatch)
# ---------------------------------------------------------------------

def test_set_volume_to_40_percent_command():
    processor, voice = make_processor()

    with patch("volume_control.audio_endpoint.set_volume_percent") as mock_set:
        result = processor.process("set volume to 40 percent")

    assert result is True
    mock_set.assert_called_once_with(40)


def test_set_volume_to_40_percent_sign_command():
    processor, voice = make_processor()

    with patch("volume_control.audio_endpoint.set_volume_percent") as mock_set:
        result = processor.process("set volume to 40%")

    assert result is True
    mock_set.assert_called_once_with(40)


def test_unmute_command_uses_true_unmute():
    processor, voice = make_processor()

    with patch("volume_control.audio_endpoint.set_mute") as mock_set_mute:
        result = processor.process("unmute")

    assert result is True
    mock_set_mute.assert_called_once_with(False)


def test_set_volume_out_of_range_never_reaches_core_audio():
    processor, voice = make_processor()

    with patch("volume_control.audio_endpoint.set_volume_percent") as mock_set:
        result = processor.process("set volume to 150 percent")

    assert result is True
    mock_set.assert_not_called()
    assert "don't know how to do that" in voice.spoken[-1]


def test_set_volume_huge_number_never_reaches_core_audio():
    processor, voice = make_processor()

    with patch("volume_control.audio_endpoint.set_volume_percent") as mock_set:
        result = processor.process(
            "set volume to 999999999999999999 percent"
        )

    assert result is True
    mock_set.assert_not_called()
    assert "don't know how to do that" in voice.spoken[-1]


def test_set_volume_negative_never_reaches_core_audio():
    processor, voice = make_processor()

    with patch("volume_control.audio_endpoint.set_volume_percent") as mock_set:
        result = processor.process("set volume to -10 percent")

    assert result is True
    mock_set.assert_not_called()
    assert "don't know how to do that" in voice.spoken[-1]


def test_set_volume_decimal_never_reaches_core_audio():
    processor, voice = make_processor()

    with patch("volume_control.audio_endpoint.set_volume_percent") as mock_set:
        result = processor.process("set volume to 40.5 percent")

    assert result is True
    mock_set.assert_not_called()
    assert "don't know how to do that" in voice.spoken[-1]


def test_set_volume_spelled_out_number_never_reaches_core_audio():
    processor, voice = make_processor()

    with patch("volume_control.audio_endpoint.set_volume_percent") as mock_set:
        result = processor.process("set volume to forty percent")

    assert result is True
    mock_set.assert_not_called()
    assert "don't know how to do that" in voice.spoken[-1]


# ---------------------------------------------------------------------
# PHASE 3: media control
# ---------------------------------------------------------------------

def test_next_track_command():
    processor, voice = make_processor()

    with patch("media_control.input_control.press_key") as mock_press:
        result = processor.process("next track")

    assert result is True
    mock_press.assert_called_once_with(
        media_control.input_control.VK_MEDIA_NEXT_TRACK
    )


# ---------------------------------------------------------------------
# PHASE 3: screenshot
# ---------------------------------------------------------------------

def test_take_screenshot_command():
    processor, voice = make_processor()

    with patch("screen_control.os.makedirs"), \
         patch("screen_control.ImageGrab.grab") as mock_grab:
        result = processor.process("take a screenshot")

    assert result is True
    mock_grab.assert_called_once()


# ---------------------------------------------------------------------
# PHASE 3: keyboard control
# ---------------------------------------------------------------------

def test_press_enter_command():
    processor, voice = make_processor()

    with patch("keyboard_control.input_control.press_key") as mock_press:
        result = processor.process("press enter")

    assert result is True
    mock_press.assert_called_once_with(keyboard_control.input_control.VK_RETURN)


def test_copy_command():
    processor, voice = make_processor()

    with patch("keyboard_control.input_control.press_key_combo") as mock_combo:
        result = processor.process("copy")

    assert result is True
    mock_combo.assert_called_once()
