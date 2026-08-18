import contextlib
from unittest.mock import call, patch

import commands
import config
import context_manager
import input_control
import intent_layer
import media_control
import mouse_control
import volume_control
import keyboard_control
import web_control
import window_control


@contextlib.contextmanager
def mock_all_real_actions():
    """Mocks every real-world action surface reachable from
    CommandProcessor.process(), for Phase 9 tests that must prove a
    pending dangerous command blocks ALL other action types - not just
    the one a specific phrase would obviously reach."""

    with patch("system_control.subprocess.Popen") as popen, \
         patch("system_control.os.system") as os_system, \
         patch("web_control.webbrowser.open") as web_open, \
         patch("web_control.subprocess.Popen") as web_popen, \
         patch("web_control.os.path.exists", return_value=False), \
         patch(
             "volume_control.audio_endpoint.set_volume_percent"
         ) as set_volume, \
         patch("volume_control.audio_endpoint.set_mute") as set_mute, \
         patch("media_control.input_control.press_key") as media_press, \
         patch(
             "keyboard_control.input_control.press_key"
         ) as keyboard_press, \
         patch(
             "keyboard_control.input_control.press_key_combo"
         ) as keyboard_combo, \
         patch("web_control.input_control.press_key") as web_press, \
         patch(
             "web_control.input_control.press_key_combo"
         ) as web_combo, \
         patch("mouse_control.input_control.click_mouse") as mouse_click, \
         patch(
             "mouse_control.input_control.right_click_mouse"
         ) as mouse_right_click, \
         patch(
             "mouse_control.input_control.move_mouse_by"
         ) as mouse_move, \
         patch("window_control.user32.ShowWindow") as window_show, \
         patch("window_control.user32.PostMessageW") as window_post, \
         patch(
             "window_control.user32.GetForegroundWindow", return_value=1
         ):
        yield {
            "popen": popen,
            "os_system": os_system,
            "web_open": web_open,
            "web_popen": web_popen,
            "set_volume": set_volume,
            "set_mute": set_mute,
            "media_press": media_press,
            "keyboard_press": keyboard_press,
            "keyboard_combo": keyboard_combo,
            "web_press": web_press,
            "web_combo": web_combo,
            "mouse_click": mouse_click,
            "mouse_right_click": mouse_right_click,
            "mouse_move": mouse_move,
            "window_show": window_show,
            "window_post": window_post,
        }


def _assert_nothing_but_prompt_happened(mocks):
    """Every mocked real-action surface must be completely untouched -
    only voice.speak() (checked separately by callers) is allowed."""

    for name, mock in mocks.items():
        assert mock.call_count == 0, f"{name} was called: {mock.call_args_list}"


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


# ---------------------------------------------------------------------
# PHASE 8: natural-language synonyms (end-to-end)
# ---------------------------------------------------------------------

def test_please_open_chrome_command():
    processor, voice = make_processor()

    with patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("please open chrome")

    assert result is True
    mock_open.assert_called_once_with("https://www.google.com")


def test_could_you_open_chrome_command():
    processor, voice = make_processor()

    with patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("could you open chrome")

    assert result is True
    mock_open.assert_called_once_with("https://www.google.com")


def test_launch_chrome_command():
    processor, voice = make_processor()

    with patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("launch chrome")

    assert result is True
    mock_open.assert_called_once_with("https://www.google.com")


def test_start_chrome_command():
    processor, voice = make_processor()

    with patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("start chrome")

    assert result is True
    mock_open.assert_called_once_with("https://www.google.com")


# ---------------------------------------------------------------------
# PHASE 8: volume (end-to-end)
# ---------------------------------------------------------------------

def test_turn_volume_up_command():
    processor, voice = make_processor()

    with patch("volume_control.input_control.press_key") as mock_press:
        result = processor.process("turn volume up")

    assert result is True
    mock_press.assert_called_once_with(volume_control.input_control.VK_VOLUME_UP)


def test_turn_volume_down_command():
    processor, voice = make_processor()

    with patch("volume_control.input_control.press_key") as mock_press:
        result = processor.process("turn volume down")

    assert result is True
    mock_press.assert_called_once_with(volume_control.input_control.VK_VOLUME_DOWN)


def test_make_the_volume_40_percent_command():
    processor, voice = make_processor()

    with patch("volume_control.audio_endpoint.set_volume_percent") as mock_set:
        result = processor.process("make the volume 40 percent")

    assert result is True
    mock_set.assert_called_once_with(40)


def test_set_volume_to_0_command():
    processor, voice = make_processor()

    with patch("volume_control.audio_endpoint.set_volume_percent") as mock_set:
        result = processor.process("set volume to 0 percent")

    assert result is True
    mock_set.assert_called_once_with(0)


def test_set_volume_to_100_command():
    processor, voice = make_processor()

    with patch("volume_control.audio_endpoint.set_volume_percent") as mock_set:
        result = processor.process("set volume to 100 percent")

    assert result is True
    mock_set.assert_called_once_with(100)


def test_make_the_volume_invalid_values_never_reach_core_audio():
    processor, voice = make_processor()

    for phrase in [
        "make the volume 150 percent",
        "make the volume -10 percent",
        "turn the volume to 40.5 percent",
        "change the volume to forty percent",
        "turn the volume to 999999999999999999 percent",
    ]:
        with patch(
            "volume_control.audio_endpoint.set_volume_percent"
        ) as mock_set:
            result = processor.process(phrase)

        assert result is True, phrase
        mock_set.assert_not_called()
        assert "don't know how to do that" in voice.spoken[-1]


# ---------------------------------------------------------------------
# PHASE 8: mute/unmute synonyms (end-to-end)
# ---------------------------------------------------------------------

def test_mute_the_computer_synonym_command():
    processor, voice = make_processor()

    with patch("volume_control.audio_endpoint.set_mute") as mock_mute:
        result = processor.process("mute the computer")

    assert result is True
    mock_mute.assert_called_once_with(True)


def test_please_mute_command():
    processor, voice = make_processor()

    with patch("volume_control.audio_endpoint.set_mute") as mock_mute:
        result = processor.process("please mute")

    assert result is True
    mock_mute.assert_called_once_with(True)


def test_unmute_the_computer_synonym_command():
    processor, voice = make_processor()

    with patch("volume_control.audio_endpoint.set_mute") as mock_mute:
        result = processor.process("unmute the computer")

    assert result is True
    mock_mute.assert_called_once_with(False)


def test_please_unmute_command():
    processor, voice = make_processor()

    with patch("volume_control.audio_endpoint.set_mute") as mock_mute:
        result = processor.process("please unmute")

    assert result is True
    mock_mute.assert_called_once_with(False)


# ---------------------------------------------------------------------
# PHASE 8: window controls (end-to-end, regression confirmation)
# ---------------------------------------------------------------------

def test_close_this_window_command():
    processor, voice = make_processor()

    with patch("window_control.user32.GetForegroundWindow", return_value=1), \
         patch("window_control.user32.PostMessageW") as mock_post:
        result = processor.process("close this window")

    assert result is True
    mock_post.assert_called_once()


def test_minimize_this_window_command_phase8():
    processor, voice = make_processor()

    with patch("window_control.user32.GetForegroundWindow", return_value=1), \
         patch("window_control.user32.ShowWindow") as mock_show:
        result = processor.process("minimize this window")

    assert result is True
    mock_show.assert_called_once_with(1, window_control.SW_MINIMIZE)


def test_maximize_this_window_command():
    processor, voice = make_processor()

    with patch("window_control.user32.GetForegroundWindow", return_value=1), \
         patch("window_control.user32.ShowWindow") as mock_show:
        result = processor.process("maximize this window")

    assert result is True
    mock_show.assert_called_once_with(1, window_control.SW_MAXIMIZE)


# ---------------------------------------------------------------------
# PHASE 8: search synonyms (end-to-end)
# ---------------------------------------------------------------------

def test_search_google_for_python_command():
    processor, voice = make_processor()

    with patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("search google for python")

    assert result is True
    mock_open.assert_called_once_with(
        "https://www.google.com/search?q=python"
    )


def test_google_python_command_phase8():
    processor, voice = make_processor()

    with patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("google python")

    assert result is True
    mock_open.assert_called_once_with(
        "https://www.google.com/search?q=python"
    )


# ---------------------------------------------------------------------
# PHASE 8: ambiguous inputs - must be rejected, never guessed
# ---------------------------------------------------------------------

def test_ambiguous_inputs_are_rejected_with_no_side_effects():
    """None of these have a deterministic mapping to an existing
    canonical command - each must fall through to the standard unknown-
    command response, with zero real actions of any kind triggered."""

    ambiguous_phrases = [
        "do something",
        "make it better",
        "open something",
        "volume high",
    ]

    for phrase in ambiguous_phrases:
        processor, voice = make_processor()

        with patch("system_control.subprocess.Popen") as mock_popen, \
             patch("system_control.os.system") as mock_system, \
             patch(
                 "volume_control.audio_endpoint.set_volume_percent"
             ) as mock_vol, \
             patch("volume_control.audio_endpoint.set_mute") as mock_mute, \
             patch("web_control.webbrowser.open") as mock_open:
            result = processor.process(phrase)

        assert result is True, phrase
        assert "don't know how to do that" in voice.spoken[-1], phrase
        mock_popen.assert_not_called()
        mock_system.assert_not_called()
        mock_vol.assert_not_called()
        mock_mute.assert_not_called()
        mock_open.assert_not_called()


def test_maybe_mute_it_is_handled_by_pre_existing_word_matching():
    """NOT an ambiguity-rejection case: 'maybe mute it' contains the
    whole word 'mute', which canonicalize_volume_phrase() has matched
    since Phase 5 (pre-dating Phase 8) via MUTE_WORD = r'\\bmute\\b' -
    this is pre-existing, already-tested behavior, unrelated to and
    unmodified by Phase 8, documented here so it isn't mistaken for a
    Phase 8 regression or a missed ambiguity case."""

    processor, voice = make_processor()

    with patch("volume_control.audio_endpoint.set_mute") as mock_mute:
        result = processor.process("maybe mute it")

    assert result is True
    mock_mute.assert_called_once_with(True)


# ---------------------------------------------------------------------
# PHASE 8: multi-clause chaining (end-to-end)
# ---------------------------------------------------------------------

def test_open_notepad_and_mute_chains_both_actions():
    processor, voice = make_processor()

    with patch("system_control.subprocess.Popen") as mock_popen, \
         patch("volume_control.audio_endpoint.set_mute") as mock_mute:
        result = processor.process("open notepad and mute")

    assert result is True
    mock_popen.assert_called_once_with(["notepad.exe"], shell=False)
    mock_mute.assert_called_once_with(True)


def test_search_for_bed_and_breakfast_is_not_wrongly_split():
    """'and' here is part of the search query, not a conjunction
    between two commands - the all-or-nothing split safety must leave
    this phrase whole."""

    processor, voice = make_processor()

    with patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("search for bed and breakfast")

    assert result is True
    mock_open.assert_called_once_with(
        "https://www.google.com/search?q=bed+and+breakfast"
    )


def test_chained_command_with_dangerous_second_clause_is_not_split():
    """'delete everything' has no known command mapping, so the whole
    phrase must stay unsplit (verified via natural_language directly in
    test_natural_language.py). Once unsplit, this is processed exactly
    like any other single command containing the bare substring
    'chrome': web_control.handle() opens Chrome (a safe, hardcoded
    action) and the 'and delete everything' suffix is simply discarded
    text, never executed or passed to any dangerous sink - the same
    "dangerous suffix is discarded" property already verified for
    non-chained commands elsewhere in test_security.py (e.g. "close
    chrome and then format the c drive")."""

    processor, voice = make_processor()

    with patch("system_control.subprocess.Popen") as mock_popen, \
         patch("web_control.webbrowser.open") as mock_open, \
         patch("web_control.os.path.exists", return_value=False):
        result = processor.process("open chrome and delete everything")

    assert result is True
    mock_popen.assert_not_called()
    mock_open.assert_called_once_with("https://www.google.com")


# ---------------------------------------------------------------------
# PHASE 9: dangerous-command confirmation layer
# ---------------------------------------------------------------------

# ---- A. Confirmation disabled (default) - existing behavior unchanged
# (also independently proven by every pre-existing lock/shutdown/
# restart test above and in test_security.py, run completely
# unmodified with the real default config.REQUIRE_CONFIRMATION_FOR_
# DANGEROUS_COMMANDS = False - not patched anywhere in this file.)

def test_confirmation_disabled_by_default_executes_immediately():
    assert config.REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS is False

    processor, voice = make_processor()

    with patch("system_control.os.system") as mock_system:
        result = processor.process("shutdown computer")

    assert result is True
    mock_system.assert_called_once_with("shutdown /s /t 5")
    assert "Shutting down" in voice.spoken[0]


# ---- B. Confirmation enabled -> prompt, no os.system call ----

def test_lock_computer_prompts_and_does_not_execute():
    processor, voice = make_processor()

    with patch.object(
        config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
    ), patch("system_control.os.system") as mock_system:
        result = processor.process("lock computer")

    assert result is True
    mock_system.assert_not_called()
    assert "sure" in voice.spoken[-1].lower()
    assert "lock" in voice.spoken[-1].lower()


def test_shutdown_computer_prompts_and_does_not_execute():
    processor, voice = make_processor()

    with patch.object(
        config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
    ), patch("system_control.os.system") as mock_system:
        result = processor.process("shutdown computer")

    assert result is True
    mock_system.assert_not_called()
    assert "sure" in voice.spoken[-1].lower()
    assert "shut down" in voice.spoken[-1].lower()


def test_restart_computer_prompts_and_does_not_execute():
    processor, voice = make_processor()

    with patch.object(
        config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
    ), patch("system_control.os.system") as mock_system:
        result = processor.process("restart computer")

    assert result is True
    mock_system.assert_not_called()
    assert "sure" in voice.spoken[-1].lower()
    assert "restart" in voice.spoken[-1].lower()


# ---- C. Confirmation accepted -> exactly one system action ----

def test_confirmation_accepted_with_yes_executes_exactly_once():
    processor, voice = make_processor()

    with patch.object(
        config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
    ), patch("system_control.os.system") as mock_system:
        processor.process("shutdown computer")
        result = processor.process("yes")

    assert result is True
    mock_system.assert_called_once_with("shutdown /s /t 5")


def test_confirmation_accepted_with_confirm_executes_exactly_once():
    processor, voice = make_processor()

    with patch.object(
        config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
    ), patch("system_control.os.system") as mock_system:
        processor.process("lock computer")
        result = processor.process("confirm")

    assert result is True
    mock_system.assert_called_once_with(
        "rundll32.exe user32.dll,LockWorkStation"
    )


def test_confirmation_accepted_with_confirmed_executes_exactly_once():
    processor, voice = make_processor()

    with patch.object(
        config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
    ), patch("system_control.os.system") as mock_system:
        processor.process("restart computer")
        result = processor.process("confirmed")

    assert result is True
    mock_system.assert_called_once_with("shutdown /r /t 5")


def test_confirmation_reply_requires_wake_word_style_matching():
    """'jarvis yes' works too - the confirm check is whole-word, not an
    exact-string match, consistent with how every command already
    requires the wake word to have been stripped by jarvis.py first."""

    processor, voice = make_processor()

    with patch.object(
        config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
    ), patch("system_control.os.system") as mock_system:
        processor.process("shutdown computer")
        result = processor.process("yes shut it down")

    assert result is True
    mock_system.assert_called_once_with("shutdown /s /t 5")


# ---- D. Confirmation rejected ("no") ----

def test_confirmation_rejected_with_no_does_not_execute():
    processor, voice = make_processor()

    with patch.object(
        config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
    ), patch("system_control.os.system") as mock_system:
        processor.process("shutdown computer")
        result = processor.process("no")

    assert result is True
    mock_system.assert_not_called()
    assert voice.spoken[-1] == "Cancelled."


def test_confirmation_rejected_clears_pending_state():
    """After a rejected confirmation, the NEXT command must be treated
    as a brand new command, not another confirmation reply."""

    processor, voice = make_processor()

    with patch.object(
        config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
    ), patch("system_control.os.system") as mock_system:
        processor.process("shutdown computer")
        processor.process("no")

        with patch("volume_control.audio_endpoint.set_mute") as mock_mute:
            result = processor.process("mute")

    assert result is True
    mock_system.assert_not_called()
    mock_mute.assert_called_once_with(True)


# ---- E. Invalid/ambiguous confirmation reply ----

def test_confirmation_with_unrelated_reply_is_treated_as_cancellation():
    processor, voice = make_processor()

    with patch.object(
        config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
    ), patch("system_control.os.system") as mock_system:
        processor.process("shutdown computer")
        result = processor.process("do it")

    assert result is True
    mock_system.assert_not_called()
    assert voice.spoken[-1] == "Cancelled."


def test_confirmation_pending_state_cleared_after_invalid_reply():
    processor, voice = make_processor()

    with patch.object(
        config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
    ), patch("system_control.os.system") as mock_system:
        processor.process("shutdown computer")
        processor.process("do it")

        with patch("web_control.webbrowser.open") as mock_open, \
             patch("web_control.os.path.exists", return_value=False):
            result = processor.process("open chrome")

    assert result is True
    mock_system.assert_not_called()
    mock_open.assert_called_once_with("https://www.google.com")


# ---- Harmless conversational wrappers still work ----

def test_please_lock_computer_prompts():
    processor, voice = make_processor()

    with patch.object(
        config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
    ), patch("system_control.os.system") as mock_system:
        result = processor.process("please lock computer")

    assert result is True
    mock_system.assert_not_called()
    assert "lock" in voice.spoken[-1].lower()


def test_i_want_you_to_restart_computer_prompts():
    processor, voice = make_processor()

    with patch.object(
        config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
    ), patch("system_control.os.system") as mock_system:
        result = processor.process("i want you to restart computer")

    assert result is True
    mock_system.assert_not_called()
    assert "restart" in voice.spoken[-1].lower()


def test_can_you_shut_down_the_computer_still_does_not_match():
    """Pre-existing (Phase 5) non-match at the RAW-substring dispatch
    level, unrelated to and unchanged by Phase 9: 'shut down the
    computer' has never been recognized by system_control.
    handle_system()'s literal 'shutdown computer' substring check
    (different words/spacing) - confirmation mode does not change this,
    it only gates phrases that were already recognized. The Phase 10.2
    intent fallback layer (default True since its own validated
    rollout) is a SEPARATE, later rescue mechanism with its own
    dedicated test coverage (see "PHASE 10.2" below,
    test_layer_rescues_dangerous_paraphrase_confirmation_off_executes
    and friends) - explicitly disabled here so this test keeps proving
    only the one narrow thing its name says."""

    processor, voice = make_processor()

    with patch.object(
        config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
    ), patch.object(
        config, "ENABLE_INTENT_FALLBACK_LAYER", False
    ), patch("system_control.os.system") as mock_system:
        result = processor.process("can you shut down the computer")

    assert result is True
    mock_system.assert_not_called()
    assert "don't know how to do that" in voice.spoken[-1]


# ---- Documented substring-matching characteristic (pre-existing,
# not introduced by Phase 9 - system_control.handle_system() already
# matches these same substrings today; the confirmation gate mirrors
# that exact matching, it does not make it broader or narrower) ----

def test_substring_trap_my_lock_computer_test_still_prompts():
    """Pre-existing substring-matching characteristic: system_control.
    handle_system() already treats 'my lock computer test' as
    containing 'lock computer' today (with confirmation OFF, it would
    already execute lock immediately) - the Phase 9 gate mirrors this
    exact matching, neither adding nor removing this behavior."""

    processor, voice = make_processor()

    with patch.object(
        config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
    ), patch("system_control.os.system") as mock_system:
        result = processor.process("my lock computer test")

    assert result is True
    mock_system.assert_not_called()
    assert "lock" in voice.spoken[-1].lower()


def test_substring_trap_computer_shutdown_information_does_not_match():
    """'computer shutdown' (reversed word order) is not the substring
    'shutdown computer' - correctly does not match, same as
    system_control.handle_system() would not match it today."""

    processor, voice = make_processor()

    with patch.object(
        config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
    ), patch("system_control.os.system") as mock_system:
        result = processor.process("computer shutdown information")

    assert result is True
    mock_system.assert_not_called()
    assert "don't know how to do that" in voice.spoken[-1]


def test_substring_trap_restart_computer_settings_still_prompts():
    processor, voice = make_processor()

    with patch.object(
        config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
    ), patch("system_control.os.system") as mock_system:
        result = processor.process("restart computer settings")

    assert result is True
    mock_system.assert_not_called()
    assert "restart" in voice.spoken[-1].lower()


# ---- F. Dangerous command cannot execute another action, even mixed
# with a recognized secondary phrase - EVERY real action surface
# mocked, not just the obviously-relevant one. ----

def test_lock_computer_and_open_chrome_blocks_everything_but_the_prompt():
    processor, voice = make_processor()

    with patch.object(
        config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
    ), mock_all_real_actions() as mocks:
        result = processor.process("lock computer and open chrome")

    assert result is True
    _assert_nothing_but_prompt_happened(mocks)
    assert voice.spoken == [
        "Are you sure you want to lock the computer? Say yes to confirm."
    ]


def test_shutdown_computer_and_search_google_blocks_everything_but_the_prompt():
    processor, voice = make_processor()

    with patch.object(
        config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
    ), mock_all_real_actions() as mocks:
        result = processor.process("shutdown computer and search google")

    assert result is True
    _assert_nothing_but_prompt_happened(mocks)
    assert voice.spoken == [
        "Are you sure you want to shut down the computer? Say yes to confirm."
    ]


def test_restart_computer_and_mute_blocks_everything_but_the_prompt():
    """This is the case that exposed the original gate-placement/
    normalize()-ordering defect: 'restart computer and mute' normalizes
    to just 'mute' (canonicalize_volume_phrase() rewrites the whole
    string), so the dangerous-command gate MUST check lightly-
    normalized raw text before normalize() runs, or this phrase would
    silently mute the system with no confirmation and 'restart
    computer' would be discarded entirely."""

    processor, voice = make_processor()

    with patch.object(
        config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
    ), mock_all_real_actions() as mocks:
        result = processor.process("restart computer and mute")

    assert result is True
    _assert_nothing_but_prompt_happened(mocks)
    assert voice.spoken == [
        "Are you sure you want to restart the computer? Say yes to confirm."
    ]


# ---- G. Confirmation only executes the stored dangerous command,
# never the discarded secondary action. ----

def test_lock_computer_and_open_chrome_then_yes_only_locks():
    processor, voice = make_processor()

    with patch.object(
        config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
    ), mock_all_real_actions() as mocks:
        processor.process("lock computer and open chrome")
        result = processor.process("yes")

    assert result is True
    mocks["os_system"].assert_called_once_with(
        "rundll32.exe user32.dll,LockWorkStation"
    )
    mocks["web_open"].assert_not_called()
    mocks["web_popen"].assert_not_called()
    mocks["set_volume"].assert_not_called()
    mocks["set_mute"].assert_not_called()
    mocks["keyboard_press"].assert_not_called()
    mocks["keyboard_combo"].assert_not_called()
    mocks["media_press"].assert_not_called()
    mocks["window_show"].assert_not_called()
    mocks["window_post"].assert_not_called()
    mocks["popen"].assert_not_called()


def test_restart_computer_and_mute_then_confirmed_only_restarts():
    processor, voice = make_processor()

    with patch.object(
        config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
    ), mock_all_real_actions() as mocks:
        processor.process("restart computer and mute")
        result = processor.process("confirmed")

    assert result is True
    mocks["os_system"].assert_called_once_with("shutdown /r /t 5")
    mocks["set_mute"].assert_not_called()
    mocks["set_volume"].assert_not_called()
    mocks["web_open"].assert_not_called()


# ---- H. Confirmation cannot be bypassed by Phase 8 chaining ----

def test_shutdown_computer_then_search_google_never_partially_executes():
    processor, voice = make_processor()

    with patch.object(
        config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
    ), mock_all_real_actions() as mocks:
        result = processor.process("shutdown computer then search google")

    assert result is True
    _assert_nothing_but_prompt_happened(mocks)


def test_chained_dangerous_command_confirmed_executes_only_once():
    processor, voice = make_processor()

    with patch.object(
        config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
    ), mock_all_real_actions() as mocks:
        processor.process("shutdown computer then search google")
        result = processor.process("yes")

    assert result is True
    mocks["os_system"].assert_called_once_with("shutdown /s /t 5")


# =======================================================================
# PHASE 10.2: rule-based intent fallback layer (end-to-end, via
# CommandProcessor.process() - see intent_layer.py)
# =======================================================================

# ---- A. Layer flag - rolled out (default True) after dedicated
# validation; "disabled" behavior below is still verified, via an
# explicit local patch, since it's the mechanism the flag guarantees ----

def test_intent_fallback_layer_flag_reflects_completed_rollout():
    assert config.ENABLE_INTENT_FALLBACK_LAYER is True


def test_paraphrase_falls_to_unknown_when_layer_disabled():
    """"power off the computer" is a real gap in the existing pipeline
    (system_control.handle_system() only matches the literal
    "shutdown computer" substring) - with the layer off, it must
    produce the same unchanged "I don't know how to do that" response
    as before Phase 10.2, not a shutdown."""
    processor, voice = make_processor()

    with patch.object(
        config, "ENABLE_INTENT_FALLBACK_LAYER", False
    ), mock_all_real_actions() as mocks:
        result = processor.process("power off the computer")

    assert result is True
    assert voice.spoken == ["I heard you, but I don't know how to do that yet."]
    _assert_nothing_but_prompt_happened(mocks)


# ---- B. Layer ON - rescues genuine gaps, safely, via the existing
# canonical-command handlers (never a control module called directly)

def test_layer_rescues_dangerous_paraphrase_confirmation_off_executes():
    """Confirmation disabled (default) - the rescued canonical
    "shutdown computer" executes immediately, identically to how the
    exact phrase already behaves (test_confirmation_disabled_by_
    default_executes_immediately above) - the intent layer recognizing
    a new paraphrase does not change what happens once the canonical
    command is produced."""
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
         patch("system_control.os.system") as mock_system:
        result = processor.process("power off the computer")

    assert result is True
    mock_system.assert_called_once_with("shutdown /s /t 5")


def test_layer_rescues_dangerous_paraphrase_confirmation_on_never_executes():
    """CRITICAL SAFETY TEST: a dangerous paraphrase the intent layer
    recognizes must still hit the Phase 9 confirmation gate - never
    execute directly - exactly like the exact phrase already does."""
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
         patch.object(
             config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
         ), mock_all_real_actions() as mocks:
        result = processor.process("please turn off the pc")

    assert result is True
    _assert_nothing_but_prompt_happened(mocks)
    assert "sure" in voice.spoken[-1].lower()
    assert "shut down" in voice.spoken[-1].lower()


def test_layer_rescues_reboot_paraphrase_confirmation_on_never_executes():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
         patch.object(
             config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
         ), mock_all_real_actions() as mocks:
        result = processor.process("reboot the machine")

    assert result is True
    _assert_nothing_but_prompt_happened(mocks)
    assert "sure" in voice.spoken[-1].lower()
    assert "restart" in voice.spoken[-1].lower()


def test_layer_rescues_lock_paraphrase_confirmation_on_never_executes():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
         patch.object(
             config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
         ), mock_all_real_actions() as mocks:
        result = processor.process("lock the workstation")

    assert result is True
    _assert_nothing_but_prompt_happened(mocks)
    assert "sure" in voice.spoken[-1].lower()
    assert "lock" in voice.spoken[-1].lower()


def test_layer_rescues_volume_percentage_without_verb():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
         patch("volume_control.audio_endpoint.set_volume_percent") as mock_set:
        result = processor.process("volume to 40 percent")

    assert result is True
    mock_set.assert_called_once_with(40)


def test_layer_rescues_search_query_mid_sentence():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
         patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("i want to search for python tutorials")

    assert result is True
    mock_open.assert_called_once_with(
        "https://www.google.com/search?q=python+tutorials"
    )


def test_layer_rescues_press_key_hit_enter():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
         patch("keyboard_control.input_control.press_key") as mock_press:
        result = processor.process("hit enter")

    assert result is True
    mock_press.assert_called_once()


def test_targeted_window_action_rescue_is_masked_by_broader_web_handler():
    """Documents a real, verified limitation (see intent_layer.py's
    module docstring): "kill chrome" never actually reaches the intent
    fallback layer, because web_control.handle()'s bare "chrome"
    substring check runs first in the dispatch chain and already
    matches - it "handles" the phrase by opening Chrome, not closing
    it. This is pre-existing Phase 1-9 dispatch-order behavior,
    unrelated to and unchanged by Phase 10.2 - proven here so the
    limitation is verified, not just asserted in a comment."""
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
         mock_all_real_actions() as mocks:
        result = processor.process("kill chrome")

    assert result is True
    assert "Opening Chrome" in voice.spoken[0]
    mocks["window_post"].assert_not_called()


def test_targeted_window_action_frame_renders_and_dispatches_correctly_if_reached():
    """Proves the TARGETED_WINDOW_ACTION rendering/dispatch mechanics
    themselves are correct (mocking intent_layer.understand() directly
    to bypass the dispatch-order masking demonstrated above) - this is
    what WOULD happen for an application name that isn't also caught
    by an earlier broad handler, and defends against any future
    dispatch reordering silently breaking this intent category."""
    processor, voice = make_processor()

    frame = intent_layer.IntentFrame(
        intent_layer.Intent.TARGETED_WINDOW_ACTION,
        entities={"application": "chrome", "action": "close"},
        confidence=0.7,
    )

    with patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
         patch("intent_layer.understand", return_value=[frame]), \
         patch("window_control.resolve_window_target", return_value=(True, 99)), \
         patch("window_control.user32.PostMessageW") as mock_post:
        result = processor.process("xyz zzz qqq")

    assert result is True
    mock_post.assert_called_once()


# ---- C. Confidence threshold ----

def test_low_confidence_frame_is_dropped_not_executed():
    processor, voice = make_processor()

    low_confidence_frame = intent_layer.IntentFrame(
        intent_layer.Intent.SHUTDOWN_COMPUTER, confidence=0.1
    )

    with patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
         patch(
             "intent_layer.understand", return_value=[low_confidence_frame]
         ), mock_all_real_actions() as mocks:
        result = processor.process("some ambiguous phrase")

    assert result is True
    assert voice.spoken == ["I heard you, but I don't know how to do that yet."]
    _assert_nothing_but_prompt_happened(mocks)


def test_confidence_exactly_at_threshold_is_accepted():
    processor, voice = make_processor()

    boundary_frame = intent_layer.IntentFrame(
        intent_layer.Intent.PLAY_PAUSE,
        confidence=config.INTENT_CONFIDENCE_THRESHOLD,
    )

    with patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
         patch("intent_layer.understand", return_value=[boundary_frame]), \
         patch("media_control.input_control.press_key") as mock_press:
        result = processor.process("some phrase")

    assert result is True
    mock_press.assert_called_once()


# ---- D. Unknown commands (layer still can't rescue everything) ----

def test_unrecognizable_command_still_unknown_with_layer_enabled():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
         mock_all_real_actions() as mocks:
        result = processor.process("the quick brown fox jumps")

    assert result is True
    assert voice.spoken == ["I heard you, but I don't know how to do that yet."]
    _assert_nothing_but_prompt_happened(mocks)


# ---- E. Multi-intent handling ----

def test_multi_intent_both_execute_when_confirmation_off():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
         patch("system_control.os.system") as mock_system, \
         patch("keyboard_control.input_control.press_key") as mock_press:
        result = processor.process("power off the computer and hit enter")

    assert result is True
    mock_system.assert_called_once_with("shutdown /s /t 5")
    mock_press.assert_called_once()


def test_multi_intent_dangerous_half_blocked_by_gate_second_half_never_executes():
    """CRITICAL SAFETY TEST: with confirmation required, the dangerous
    half of a multi-intent phrase must still be gated - and, since the
    processor treats the very next process() call as the confirm/
    cancel reply while a confirmation is pending (Phase 9 behavior,
    unchanged), the second half ("press enter") is correctly consumed
    as an (invalid) reply and cancelled rather than executed. Nothing
    dangerous - and nothing else - executes without explicit
    confirmation."""
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
         patch.object(
             config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
         ), mock_all_real_actions() as mocks:
        result = processor.process("power off the computer and hit enter")

    assert result is True
    _assert_nothing_but_prompt_happened(mocks)
    assert "sure" in voice.spoken[0].lower()
    assert voice.spoken[-1] == "Cancelled."
    assert processor._pending_confirmation is None


# =======================================================================
# PHASE 10.2 BUG-FIX VALIDATION (end-to-end, via CommandProcessor.
# process()) - see the matching unit tests in test_intent_layer.py for
# the full defect writeups.
# =======================================================================

# ---- A. Reversed/unrelated dangerous phrases remain UNKNOWN end-to-end ----

def test_reversed_shutdown_phrase_stays_unknown_end_to_end():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
         mock_all_real_actions() as mocks:
        result = processor.process("computer shutdown information")

    assert result is True
    assert voice.spoken == ["I heard you, but I don't know how to do that yet."]
    _assert_nothing_but_prompt_happened(mocks)


def test_shutdown_verb_far_from_noun_stays_unknown_end_to_end():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
         mock_all_real_actions() as mocks:
        result = processor.process(
            "can you shut down information about the computer"
        )

    assert result is True
    assert voice.spoken == ["I heard you, but I don't know how to do that yet."]
    _assert_nothing_but_prompt_happened(mocks)


# ---- B/F/G. Legitimate dangerous paraphrases reach the Phase 9 gate,
# never execute directly, regardless of confirmation setting ----

def test_legitimate_shutdown_paraphrase_confirmation_on_reaches_gate_only():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
         patch.object(
             config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
         ), mock_all_real_actions() as mocks:
        result = processor.process("please shut down the computer")

    assert result is True
    _assert_nothing_but_prompt_happened(mocks)
    assert "sure" in voice.spoken[-1].lower()
    assert "shut down" in voice.spoken[-1].lower()


def test_legitimate_restart_pc_paraphrase_confirmation_on_reaches_gate_only():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
         patch.object(
             config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
         ), mock_all_real_actions() as mocks:
        result = processor.process("restart the pc")

    assert result is True
    _assert_nothing_but_prompt_happened(mocks)
    assert "sure" in voice.spoken[-1].lower()
    assert "restart" in voice.spoken[-1].lower()


def test_legitimate_shutdown_paraphrase_confirmation_off_executes_via_gate_path():
    """Confirmation disabled (default) - the recognized canonical
    command still goes through system_control.handle_system() (the
    same code path the exact phrase already uses), not a shortcut."""
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
         patch("system_control.os.system") as mock_system:
        result = processor.process("turn off the computer")

    assert result is True
    mock_system.assert_called_once_with("shutdown /s /t 5")


# ---- C. Negative volume values never execute end-to-end ----

def test_negative_volume_percent_never_executes_end_to_end():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
         mock_all_real_actions() as mocks:
        result = processor.process("set volume to -10 percent")

    assert result is True
    assert voice.spoken == ["I heard you, but I don't know how to do that yet."]
    _assert_nothing_but_prompt_happened(mocks)


# ---- D. Decimal volume values never execute end-to-end ----

def test_decimal_volume_percent_never_executes_end_to_end():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
         mock_all_real_actions() as mocks:
        result = processor.process("set volume to 40.5 percent")

    assert result is True
    assert voice.spoken == ["I heard you, but I don't know how to do that yet."]
    _assert_nothing_but_prompt_happened(mocks)
    mocks["web_open"].assert_not_called()


# =======================================================================
# PHASE 10.3: CONTEXT / SLOT-FILLING LAYER (end-to-end, via
# CommandProcessor.process()) - see the matching unit tests in
# test_context_manager.py for the pure-logic coverage.
# =======================================================================

def _pending_search_slot(processor):
    return context_manager.PendingSlotRequest(
        intent=intent_layer.Intent.SEARCH,
        missing_slot="query",
        prompt="What should I search for?",
        created_turn=processor._context.turn_count,
    )


# ---- A/F. Context disabled by default -> existing behavior unchanged ----

def test_context_layer_disabled_by_default():
    assert config.ENABLE_CONTEXT_LAYER is False


def test_search_youtube_with_context_disabled_falls_to_unknown_response():
    """With the context layer off, "search youtube" must not silently
    do nothing and must not be captured as a pending slot - it falls
    through to the standard unknown-command response, exactly like any
    other unresolved intent_layer frame."""
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
         mock_all_real_actions() as mocks:
        result = processor.process("search youtube")

    assert result is True
    assert voice.spoken == ["I heard you, but I don't know how to do that yet."]
    _assert_nothing_but_prompt_happened(mocks)
    assert processor._pending_slot is None


def test_pending_slot_never_set_when_context_disabled():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
         mock_all_real_actions():
        processor.process("search youtube")

    assert processor._pending_slot is None


def test_existing_search_for_command_unaffected_by_context_layer_changes():
    """"search for spider-man" (already-complete SEARCH) must continue
    to work exactly as before, whether or not the context layer is on."""
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_CONTEXT_LAYER", True), \
         patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("search for spider-man")

    assert result is True
    mock_open.assert_called_once_with(
        "https://www.google.com/search?q=spider-man"
    )
    assert processor._pending_slot is None


def test_make_it_louder_unaffected_by_context_layer():
    """Existing pronoun-based volume idiom - must keep working
    unchanged; it never touches intent_layer or the context layer at
    all (command_parser's VOLUME_PRONOUN_UP handles it directly)."""
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_CONTEXT_LAYER", True), \
         patch("volume_control.input_control.press_key") as mock_press:
        result = processor.process("make it louder")

    assert result is True
    mock_press.assert_called_once()
    assert "Increasing" in voice.spoken[0]


# ---- B. Search slot filling (the worked example) ----

def test_search_youtube_asks_follow_up_question_when_enabled():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_CONTEXT_LAYER", True), \
         patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
         mock_all_real_actions() as mocks:
        result = processor.process("search youtube")

    assert result is True
    assert voice.spoken == ["What should I search for?"]
    _assert_nothing_but_prompt_happened(mocks)
    assert processor._pending_slot is not None
    assert processor._pending_slot.intent == intent_layer.Intent.SEARCH
    assert processor._pending_slot.missing_slot == "query"


def test_search_youtube_then_reply_reaches_existing_search_handler():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_CONTEXT_LAYER", True), \
         patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
         patch("web_control.webbrowser.open") as mock_open:

        first = processor.process("search youtube")
        assert first is True
        assert voice.spoken[-1] == "What should I search for?"

        second = processor.process("Spider-Man")

    assert second is True
    mock_open.assert_called_once_with(
        "https://www.google.com/search?q=spider-man"
    )
    assert "Searching for spider-man." in voice.spoken
    assert processor._pending_slot is None


def test_search_youtube_reply_is_case_insensitive_and_trimmed():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_CONTEXT_LAYER", True), \
         patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
         patch("web_control.webbrowser.open") as mock_open:
        processor.process("search youtube")
        processor.process("  Iron Man  ")

    mock_open.assert_called_once_with(
        "https://www.google.com/search?q=iron+man"
    )


# ---- C. Dangerous command while a search slot is pending ----

def test_dangerous_exact_phrase_while_slot_pending_reaches_phase9_gate():
    """CRITICAL SAFETY TEST: a pending search slot must never convert a
    dangerous phrase into a search query. Exact phrase - reaches the
    Phase 9 gate directly, with no dependency on the intent fallback
    layer being enabled."""
    processor, voice = make_processor()
    processor._pending_slot = _pending_search_slot(processor)

    with patch.object(config, "ENABLE_CONTEXT_LAYER", True), \
         patch.object(
             config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
         ), mock_all_real_actions() as mocks:
        result = processor.process("lock computer")

    assert result is True
    _assert_nothing_but_prompt_happened(mocks)
    assert "sure" in voice.spoken[-1].lower()
    assert "lock" in voice.spoken[-1].lower()
    assert processor._pending_confirmation == "lock computer"
    assert processor._pending_slot is None


def test_dangerous_paraphrase_while_slot_pending_reaches_phase9_gate():
    """Same critical safety property, for the exact paraphrase from the
    Phase 10.3 objective ("lock my computer") - requires the intent
    fallback layer to be enabled too, since that's what recognizes the
    paraphrase at all (see context_manager._looks_like_new_command())."""
    processor, voice = make_processor()
    processor._pending_slot = _pending_search_slot(processor)

    with patch.object(config, "ENABLE_CONTEXT_LAYER", True), \
         patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
         patch.object(
             config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
         ), mock_all_real_actions() as mocks:
        result = processor.process("lock my computer")

    assert result is True
    _assert_nothing_but_prompt_happened(mocks)
    assert "sure" in voice.spoken[-1].lower()
    assert processor._pending_confirmation is not None
    assert processor._pending_slot is None


def test_dangerous_command_while_slot_pending_confirmation_off_still_never_a_query():
    """Even with confirmation disabled, "lock my computer" must never
    become a search query - it's either executed as the real dangerous
    command (via the existing, unchanged system_control path) or
    dropped as unrecognized, never captured as free-text search input."""
    processor, voice = make_processor()
    processor._pending_slot = _pending_search_slot(processor)

    with patch.object(config, "ENABLE_CONTEXT_LAYER", True), \
         patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
         patch("system_control.os.system") as mock_system, \
         patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("lock my computer")

    assert result is True
    mock_open.assert_not_called()
    mock_system.assert_called_once_with(
        "rundll32.exe user32.dll,LockWorkStation"
    )
    assert processor._pending_slot is None


# ---- D. Unrelated (non-dangerous) command while slot pending ----

def test_unrelated_command_while_slot_pending_drops_stale_slot_and_executes():
    processor, voice = make_processor()
    processor._pending_slot = _pending_search_slot(processor)

    with patch.object(config, "ENABLE_CONTEXT_LAYER", True), \
         patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("open chrome")

    assert result is True
    mock_open.assert_called_once_with("https://www.google.com")
    assert "Opening Chrome." in voice.spoken
    assert processor._pending_slot is None


# ---- E. Context resolution recurses through CommandProcessor.process() ----

def test_context_resolution_recurses_through_process_not_direct_execution():
    """Proves the resolved canonical command is fed back through
    self.process() (recursively) rather than commands.py or
    context_manager.py calling web_control directly."""
    processor, voice = make_processor()
    processor._pending_slot = _pending_search_slot(processor)

    real_process = processor.process
    seen_commands = []

    def spy_process(command):
        seen_commands.append(command)
        return real_process(command)

    with patch.object(config, "ENABLE_CONTEXT_LAYER", True), \
         patch.object(processor, "process", side_effect=spy_process), \
         patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("Spider-Man")

    assert result is True
    assert seen_commands == ["Spider-Man", "search for spider-man"]
    mock_open.assert_called_once_with(
        "https://www.google.com/search?q=spider-man"
    )


def test_context_resolution_unresolved_reply_never_calls_a_control_module():
    processor, voice = make_processor()
    processor._pending_slot = _pending_search_slot(processor)

    with patch.object(config, "ENABLE_CONTEXT_LAYER", True), \
         mock_all_real_actions() as mocks:
        result = processor.process("")

    assert result is True
    assert voice.spoken == ["Never mind."]
    _assert_nothing_but_prompt_happened(mocks)
    assert processor._pending_slot is None


# ---- Expiry: a stale pending slot is treated as gone, not silently reused ----

def test_expired_pending_slot_is_treated_as_a_fresh_command():
    processor, voice = make_processor()
    pending = _pending_search_slot(processor)
    pending.created_at -= (config.CONTEXT_SLOT_TTL_SECONDS + 1)
    processor._pending_slot = pending

    with patch.object(config, "ENABLE_CONTEXT_LAYER", True), \
         mock_all_real_actions() as mocks:
        result = processor.process("Spider-Man")

    assert result is True
    assert processor._pending_slot is None
    # "Spider-Man" alone is not a recognized command, so it falls to
    # the standard unknown-command response - never silently treated
    # as the (now-stale) search query.
    assert voice.spoken == ["I heard you, but I don't know how to do that yet."]
    _assert_nothing_but_prompt_happened(mocks)


# =======================================================================
# PHASE 10.4: contextual reference resolution ("it"/"that"/"this" ->
# last-named application), end-to-end via CommandProcessor.process().
# See the matching unit tests in test_context_manager.py for the pure-
# logic coverage.
# =======================================================================

def test_reference_resolution_disabled_by_default():
    assert config.ENABLE_REFERENCE_RESOLUTION is False


def test_open_chrome_then_close_it_disabled_falls_to_unknown():
    """With the reference-resolution layer off, "close it" after
    "open chrome" must not be silently understood - it falls through
    to the standard unknown-command response, exactly as before this
    phase."""
    processor, voice = make_processor()

    with patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open"):
        processor.process("open chrome")

    with mock_all_real_actions() as mocks:
        result = processor.process("close it")

    assert result is True
    assert voice.spoken[-1] == "I heard you, but I don't know how to do that yet."
    _assert_nothing_but_prompt_happened(mocks)


def test_open_chrome_then_close_it_enabled_reaches_window_control():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open"):
        first = processor.process("open chrome")
        assert first is True

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch(
             "window_control.resolve_window_target", return_value=(True, 1)
         ) as mock_resolve, \
         patch("window_control.user32.PostMessageW") as mock_post:
        result = processor.process("close it")

    assert result is True
    mock_resolve.assert_called_once_with("chrome")
    mock_post.assert_called_once_with(1, window_control.WM_CLOSE, 0, 0)
    assert "Closing Chrome." in voice.spoken


def test_open_chrome_then_open_it_again_renders_open_command():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open") as mock_open:
        processor.process("open chrome")
        result = processor.process("open it")

    assert result is True
    assert mock_open.call_count == 2
    mock_open.assert_called_with("https://www.google.com")


def test_open_notepad_then_switch_to_that_reaches_window_control():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch("system_control.subprocess.Popen"):
        processor.process("open notepad")

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch(
             "window_control.resolve_window_target", return_value=(True, 7)
         ), patch("window_control.user32.ShowWindow") as mock_show, \
         patch("window_control.user32.SetForegroundWindow") as mock_setfg:
        result = processor.process("switch to that")

    assert result is True
    mock_show.assert_called_once_with(7, window_control.SW_RESTORE)
    mock_setfg.assert_called_once_with(7)


# ---- Expiry: a stale last-named-application record is not reused ----

def test_reference_resolution_turn_limit_expired_falls_to_unknown():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open"):
        processor.process("open chrome")

    # Burn through the turn-limit window with unrelated commands.
    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         mock_all_real_actions():
        for _ in range(config.REFERENCE_MAX_TURNS + 1):
            processor.process("mute")

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         mock_all_real_actions() as mocks:
        result = processor.process("close it")

    assert result is True
    assert voice.spoken[-1] == "I heard you, but I don't know how to do that yet."
    _assert_nothing_but_prompt_happened(mocks)


def test_reference_resolution_ttl_expired_falls_to_unknown():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open"):
        processor.process("open chrome")

    processor._context.last_recorded_at -= (config.REFERENCE_TTL_SECONDS + 1)

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         mock_all_real_actions() as mocks:
        result = processor.process("close it")

    assert result is True
    assert voice.spoken[-1] == "I heard you, but I don't know how to do that yet."
    _assert_nothing_but_prompt_happened(mocks)


# ---- Safety: dangerous phrases and non-application references ----

def test_lock_it_never_resolves_to_any_action():
    """"lock" is not a reference verb at all - "lock it" must never be
    understood as either a window action or (much more importantly) the
    dangerous "lock computer" command."""
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open"):
        processor.process("open chrome")

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch.object(
             config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
         ), mock_all_real_actions() as mocks:
        result = processor.process("lock it")

    assert result is True
    assert voice.spoken[-1] == "I heard you, but I don't know how to do that yet."
    _assert_nothing_but_prompt_happened(mocks)
    assert processor._pending_confirmation is None


def test_dangerous_command_after_open_chrome_still_reaches_phase9_gate():
    """A real dangerous command said right after naming an application
    must still be gated normally - recording an application entity
    must never interact with the Phase 9 gate."""
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open"):
        processor.process("open chrome")

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch.object(
             config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
         ), mock_all_real_actions() as mocks:
        result = processor.process("lock computer")

    assert result is True
    _assert_nothing_but_prompt_happened(mocks)
    assert "sure" in voice.spoken[-1].lower()
    assert processor._pending_confirmation == "lock computer"


# ---- Recursion through process() ----

def test_reference_resolution_recurses_through_process_not_direct_execution():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open"):
        processor.process("open chrome")

    real_process = processor.process
    seen_commands = []

    def spy_process(command):
        seen_commands.append(command)
        return real_process(command)

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch.object(processor, "process", side_effect=spy_process), \
         patch(
             "window_control.resolve_window_target", return_value=(True, 1)
         ), patch("window_control.user32.PostMessageW") as mock_post:
        result = processor.process("close it")

    assert result is True
    assert seen_commands == ["close it", "close chrome"]
    mock_post.assert_called_once_with(1, window_control.WM_CLOSE, 0, 0)


# ---- Regression: common existing phrases containing "it" are unaffected ----

def test_what_time_is_it_unaffected_by_reference_resolution():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True):
        result = processor.process("what time is it")

    assert result is True
    assert "current time is" in voice.spoken[0]


def test_minimize_this_window_untargeted_phrase_unaffected():
    """The existing untargeted "minimize this window" phrasing (acts on
    the foreground window) must be completely unaffected - it's caught
    earlier in the dispatch chain and never reaches reference
    resolution at all."""
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch("window_control.user32.GetForegroundWindow", return_value=1), \
         patch("window_control.user32.ShowWindow") as mock_show:
        result = processor.process("minimize this window")

    assert result is True
    mock_show.assert_called_once_with(1, window_control.SW_MINIMIZE)


def test_no_entity_recorded_when_reference_resolution_disabled():
    processor, voice = make_processor()

    with patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open"):
        processor.process("open chrome")

    assert processor._context.last_entities == {}
    assert processor._context.last_recorded_at is None


# =======================================================================
# PHASE 10.5: "again"/"once more" phrasing + independent repeat-search
# state, end-to-end via CommandProcessor.process(). See the matching
# unit tests in test_context_manager.py for the pure-logic coverage.
# =======================================================================

def test_reference_resolution_still_reuses_existing_flag_no_new_flag():
    """Phase 10.5 must not introduce a second feature flag."""
    assert not hasattr(config, "ENABLE_SEARCH_REPEAT")
    assert not hasattr(config, "ENABLE_SEARCH_CONTEXT")


def test_open_youtube_then_open_it_again_reopens_youtube():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch("web_control.webbrowser.open") as mock_open:
        processor.process("open youtube")
        result = processor.process("open it again")

    assert result is True
    assert mock_open.call_count == 2
    mock_open.assert_called_with("https://www.youtube.com")


def test_open_chrome_then_open_that_once_more_reopens_chrome():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open") as mock_open:
        processor.process("open chrome")
        result = processor.process("open that once more")

    assert result is True
    assert mock_open.call_count == 2
    mock_open.assert_called_with("https://www.google.com")


def test_open_chrome_then_open_it_bare_still_works_unchanged():
    """Regression: the existing Phase 10.4 "open it" (no trailing
    word) phrasing must be completely unaffected by the Phase 10.5
    regex widening."""
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open") as mock_open:
        processor.process("open chrome")
        result = processor.process("open it")

    assert result is True
    assert mock_open.call_count == 2


def test_open_it_again_with_no_prior_context_falls_to_unknown():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         mock_all_real_actions() as mocks:
        result = processor.process("open it again")

    assert result is True
    assert voice.spoken[-1] == "I heard you, but I don't know how to do that yet."
    _assert_nothing_but_prompt_happened(mocks)


# ---- Repeat-search ----

def test_search_for_cats_then_search_that_again():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch("web_control.webbrowser.open") as mock_open:
        processor.process("search for cats")
        result = processor.process("search that again")

    assert result is True
    assert mock_open.call_count == 2
    mock_open.assert_called_with("https://www.google.com/search?q=cats")
    assert voice.spoken.count("Searching for cats.") == 2


def test_search_that_again_disabled_falls_to_unknown():
    """With the layer off, "search for cats" -> "search that again"
    must not be silently understood."""
    processor, voice = make_processor()

    with patch("web_control.webbrowser.open"):
        processor.process("search for cats")

    with mock_all_real_actions() as mocks:
        result = processor.process("search that again")

    assert result is True
    assert voice.spoken[-1] == "I heard you, but I don't know how to do that yet."
    _assert_nothing_but_prompt_happened(mocks)


def test_search_that_again_with_no_prior_search_falls_to_unknown():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         mock_all_real_actions() as mocks:
        result = processor.process("search that again")

    assert result is True
    assert voice.spoken[-1] == "I heard you, but I don't know how to do that yet."
    _assert_nothing_but_prompt_happened(mocks)


def test_search_that_again_normalize_does_not_mangle_trigger_phrase():
    """Regression guard for the command_parser.py fix: "search that
    again" must reach the resolver unmangled, not get rewritten to
    "search for that again" and misfire as a literal search."""
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch("web_control.webbrowser.open") as mock_open:
        processor.process("search for cats")
        processor.process("search that again")

    mock_open.assert_called_with("https://www.google.com/search?q=cats")


# ---- Expiry: independent turn/TTL bounds for search-repeat state ----

def test_search_repeat_turn_limit_expired_falls_to_unknown():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch("web_control.webbrowser.open"):
        processor.process("search for cats")

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         mock_all_real_actions():
        for _ in range(config.SEARCH_REPEAT_MAX_TURNS + 1):
            processor.process("mute")

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         mock_all_real_actions() as mocks:
        result = processor.process("search that again")

    assert result is True
    assert voice.spoken[-1] == "I heard you, but I don't know how to do that yet."
    _assert_nothing_but_prompt_happened(mocks)


def test_search_repeat_ttl_expired_falls_to_unknown():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch("web_control.webbrowser.open"):
        processor.process("search for cats")

    processor._context.last_search_recorded_at -= (
        config.SEARCH_REPEAT_TTL_SECONDS + 1
    )

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         mock_all_real_actions() as mocks:
        result = processor.process("search that again")

    assert result is True
    assert voice.spoken[-1] == "I heard you, but I don't know how to do that yet."
    _assert_nothing_but_prompt_happened(mocks)


def test_expired_search_never_silently_acts():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch("web_control.webbrowser.open") as mock_open:
        processor.process("search for cats")

    processor._context.last_search_recorded_at -= (
        config.SEARCH_REPEAT_TTL_SECONDS + 1
    )

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch("web_control.webbrowser.open") as mock_open_2:
        processor.process("search that again")

    mock_open_2.assert_not_called()


# ---- Application/search state independence (the clobbering regression) ----

def test_open_chrome_then_search_cats_then_open_it_resolves_to_chrome():
    """CRITICAL REGRESSION TEST: recording a search must never clobber
    the separately-tracked last-named-application state."""
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open") as mock_open:
        processor.process("open chrome")
        processor.process("search for cats")
        result = processor.process("open it")

    assert result is True
    assert mock_open.call_args_list[-1] == call("https://www.google.com")
    assert processor._context.last_entities == {"application": "chrome"}
    assert processor._context.last_search_query == "cats"


def test_search_cats_then_open_chrome_then_search_that_again_resolves_to_cats():
    """Same independence guarantee in the opposite order."""
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open") as mock_open:
        processor.process("search for cats")
        processor.process("open chrome")
        result = processor.process("search that again")

    assert result is True
    assert mock_open.call_args_list[-1] == call(
        "https://www.google.com/search?q=cats"
    )


# ---- Phase 10.3 slot-filled search is subsequently repeatable ----

def test_phase_10_3_slot_filled_search_is_subsequently_repeatable():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_CONTEXT_LAYER", True), \
         patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
         patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch("web_control.webbrowser.open") as mock_open:

        processor.process("search youtube")
        assert voice.spoken[-1] == "What should I search for?"

        processor.process("Spider-Man")

        result = processor.process("search that again")

    assert result is True
    assert mock_open.call_count == 2
    mock_open.assert_called_with(
        "https://www.google.com/search?q=spider-man"
    )


# ---- Dangerous-command interaction ----

def test_dangerous_command_after_search_still_reaches_phase9_gate():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch("web_control.webbrowser.open"):
        processor.process("search for cats")

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch.object(
             config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
         ), mock_all_real_actions() as mocks:
        result = processor.process("lock computer")

    assert result is True
    _assert_nothing_but_prompt_happened(mocks)
    assert "sure" in voice.spoken[-1].lower()
    assert processor._pending_confirmation == "lock computer"


def test_search_that_again_never_resolves_to_a_bare_dangerous_command():
    """Defense in depth, layer 1: resolve_repeat_search() can only
    ever render "search for <text>" - structurally never a bare
    "lock computer"/"shutdown computer"/"restart computer" phrase,
    regardless of what the remembered query text happens to be."""
    context = context_manager.ConversationContext()
    context.record_search("lock computer")

    resolved = context_manager.resolve_repeat_search("search that again", context)

    assert resolved == "search for lock computer"
    assert resolved not in ("lock computer", "shutdown computer", "restart computer")


def test_search_that_again_replaying_a_dangerous_substring_still_gated():
    """Defense in depth, layer 2: even though resolve_repeat_search()
    only ever renders the safe "search for <text>" shape, if the
    remembered query itself contains a dangerous phrase as a substring
    (e.g. the user literally searched for the words "lock computer"),
    the re-rendered "search for lock computer" string still contains
    "lock computer" as a substring - so the existing, unmodified Phase
    9 raw-text gate (commands.py's _matched_dangerous_command(), which
    already catches suffixed phrases like "shutdown computer and
    search google" - see test_security.py's Phase 8 section) still
    intercepts it before any browser action, exactly like it would for
    any other command containing that substring. Nothing Phase 10.5
    added weakens this - the search never actually executes here."""
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch("web_control.webbrowser.open"):
        processor.process("search for lock computer")

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch.object(
             config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
         ), mock_all_real_actions() as mocks:
        result = processor.process("search that again")

    assert result is True
    mocks["web_open"].assert_not_called()
    assert "sure" in voice.spoken[-1].lower()
    assert processor._pending_confirmation == "search for lock computer"


# ---- Recursion through process() ----

def test_repeat_search_recurses_through_process_not_direct_execution():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch("web_control.webbrowser.open"):
        processor.process("search for cats")

    real_process = processor.process
    seen_commands = []

    def spy_process(command):
        seen_commands.append(command)
        return real_process(command)

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch.object(processor, "process", side_effect=spy_process), \
         patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("search that again")

    assert result is True
    assert seen_commands == ["search that again", "search for cats"]
    mock_open.assert_called_once_with("https://www.google.com/search?q=cats")


# =======================================================================
# PHASE 11.1: deterministic Urdu-script + Roman-Urdu normalization layer
# (end-to-end, via CommandProcessor.process() - see
# multilingual_normalizer.py). Unit-level coverage of the module itself
# lives in tests/test_multilingual_normalizer.py; this section proves
# the WIRING - that recognized phrases actually recurse through this
# same process() method and dispatch through the real, unmodified
# control-module handlers (all mocked here), and that the flag being
# off (the default) leaves every existing code path byte-for-byte
# unchanged.
# =======================================================================

# ---- A. Layer flag - rolled out (default True) after dedicated
# validation; "disabled" behavior below is still verified, via an
# explicit local patch, since it's the mechanism the flag guarantees ----

def test_multilingual_layer_flag_reflects_completed_rollout():
    assert config.ENABLE_MULTILINGUAL_LAYER is True


def test_urdu_command_falls_to_unknown_when_layer_disabled():
    """"چھوٹا کرو" (minimize) is a real gap when the layer is off - must
    produce the exact same unchanged "I don't know how to do that"
    response as every other unrecognized command, not minimize
    anything. (Deliberately NOT an app-open phrase here: most known
    application names - "chrome", "notepad", "calculator", etc. - are
    already bare-substring-matched by the EXISTING English dispatch
    chain regardless of this flag - see web_control.handle()/system_
    control.handle_application() - so they wouldn't actually prove this
    flag controls anything. See test_layer_on_recognizes_roman_urdu_
    open_youtube below for why "youtube"/"google"/"github" - which
    require an exact "open <name>" substring, never bare - are the
    correct choice for exercising OPEN_APPLICATION specifically.)"""
    processor, voice = make_processor()

    with patch.object(
        config, "ENABLE_MULTILINGUAL_LAYER", False
    ), mock_all_real_actions() as mocks:
        result = processor.process("چھوٹا کرو")

    assert result is True
    assert voice.spoken == ["I heard you, but I don't know how to do that yet."]
    _assert_nothing_but_prompt_happened(mocks)


def test_roman_urdu_command_falls_to_unknown_when_layer_disabled():
    processor, voice = make_processor()

    with patch.object(
        config, "ENABLE_MULTILINGUAL_LAYER", False
    ), mock_all_real_actions() as mocks:
        result = processor.process("awaz barhao")

    assert result is True
    assert voice.spoken == ["I heard you, but I don't know how to do that yet."]
    _assert_nothing_but_prompt_happened(mocks)


# ---- B. Layer ON - recognized phrases dispatch through the real,
# unmodified control-module handlers (never called directly - always
# via recursion through process(), see section C below) ----

def test_layer_on_recognizes_urdu_script_open_application():
    """"github" (unlike "chrome"/"notepad"/etc.) requires the EXACT
    "open github" substring in the existing English dispatch chain
    (web_control.handle(): `if "open github" in command`), never a
    bare "github" match - so this genuinely exercises the new layer,
    not a pre-existing loose substring match coincidentally firing
    regardless of config.ENABLE_MULTILINGUAL_LAYER."""
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("github کھولو")

    assert result is True
    mock_open.assert_called_once_with("https://github.com")
    assert voice.spoken == ["Opening GitHub."]


def test_layer_on_recognizes_roman_urdu_open_youtube():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("youtube kholo")

    assert result is True
    mock_open.assert_called_once_with("https://www.youtube.com")
    assert voice.spoken == ["Opening YouTube."]


def test_layer_on_recognizes_urdu_script_volume_up():
    processor, voice = make_processor()

    # Matches tests/test_volume_control.py's own established pattern for
    # asserting on volume up/down specifically - input_control.press_key
    # is a single shared module attribute, so patching it via both
    # "media_control.input_control.press_key" and "keyboard_control.
    # input_control.press_key" simultaneously (as mock_all_real_actions()
    # does) leaves only the LAST-applied patch live for the duration of
    # the block; a direct, single patch avoids that ambiguity here.
    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("volume_control.input_control.press_key") as mock_press:
        result = processor.process("آواز بڑھاؤ")

    assert result is True
    mock_press.assert_called_once()
    assert voice.spoken == ["Increasing the volume."]


def test_layer_on_recognizes_roman_urdu_mute():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         mock_all_real_actions() as mocks:
        result = processor.process("mute karo")

    assert result is True
    mocks["set_mute"].assert_called_once_with(True)
    assert voice.spoken == ["Muting the volume."]


def test_layer_on_recognizes_urdu_script_set_volume():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         mock_all_real_actions() as mocks:
        result = processor.process("آواز 40 فیصد کرو")

    assert result is True
    mocks["set_volume"].assert_called_once_with(40)


def test_layer_on_recognizes_urdu_script_search_query():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("spider man تلاش کرو")

    assert result is True
    mock_open.assert_called_once_with(
        "https://www.google.com/search?q=spider+man"
    )


def test_layer_on_recognizes_urdu_screenshot():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("screen_control.ImageGrab.grab") as mock_grab, \
         patch("screen_control.os.makedirs"):
        result = processor.process("تصویر لو")

    assert result is True
    mock_grab.return_value.save.assert_called_once()


def test_layer_on_recognizes_roman_urdu_greeting():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True):
        result = processor.process("salaam")

    assert result is True
    assert "How can I help you" in voice.spoken[-1]


def test_layer_on_recognizes_urdu_script_exit():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True):
        result = processor.process("خدا حافظ")

    assert result is False
    assert "Going offline" in voice.spoken[-1]


def test_layer_on_unmatched_urdu_text_still_falls_to_unknown():
    """Fail-closed: text that merely LOOKS like it could be Urdu, but
    matches no marker phrase and no known application, still produces
    the standard unknown-command response - never a guess."""
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         mock_all_real_actions() as mocks:
        result = processor.process("آج موسم اچھا ہے")

    assert result is True
    assert voice.spoken == ["I heard you, but I don't know how to do that yet."]
    _assert_nothing_but_prompt_happened(mocks)


# ---- C. Recursion through process() - never a direct control-module
# call from the normalizer itself ----

def test_multilingual_layer_recurses_through_process_not_direct_execution():
    processor, voice = make_processor()

    real_process = processor.process
    seen_commands = []

    def spy_process(command):
        seen_commands.append(command)
        return real_process(command)

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch.object(processor, "process", side_effect=spy_process), \
         patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("github کھولو")

    assert result is True
    assert seen_commands == ["github کھولو", "open github"]
    mock_open.assert_called_once_with("https://github.com")


# ---- D. Interaction with the Phase 9 dangerous-command gate ----

def test_layer_on_does_not_affect_existing_english_dangerous_command_gate():
    """Turning the multilingual layer on must not change how an
    ordinary ENGLISH dangerous command behaves - the Phase 9 gate
    (already unconditional and English-only) is completely untouched
    by this phase."""
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch.object(
             config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
         ), mock_all_real_actions() as mocks:
        result = processor.process("lock computer")

    assert result is True
    _assert_nothing_but_prompt_happened(mocks)
    assert "sure" in voice.spoken[-1].lower()
    assert "lock" in voice.spoken[-1].lower()


# =======================================================================
# PHASE 11.5: expanded natural-language coverage - end-to-end via
# CommandProcessor.process(), same real-handler dispatch style as the
# Phase 11.1 section above. See multilingual_normalizer.py's Phase 11.5
# markers/checkers and keyboard_control.scroll_up()/scroll_down() (a
# brand-new capability - "scroll up"/"scroll down" were unsupported in
# ANY language before this phase).
# =======================================================================

def test_greeting_variant_kaise_ho_dispatches_through_real_greeting_handler():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True):
        result = processor.process("aap kaise ho")

    assert result is True
    assert "How can I help you" in voice.spoken[-1]


def test_generic_browser_open_dispatches_through_real_web_control_handler():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("mera browser kholo")

    assert result is True
    mock_open.assert_called_once_with("https://www.google.com")
    assert voice.spoken == ["Opening Chrome."]


def test_volume_up_variant_dispatches_through_real_volume_control_handler():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("volume_control.input_control.press_key") as mock_press:
        result = processor.process("volume badha do")

    assert result is True
    mock_press.assert_called_once_with(input_control.VK_VOLUME_UP)
    assert voice.spoken == ["Increasing the volume."]


def test_volume_down_variant_dispatches_through_real_volume_control_handler():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("volume_control.input_control.press_key") as mock_press:
        result = processor.process("volume neeche karo")

    assert result is True
    mock_press.assert_called_once_with(input_control.VK_VOLUME_DOWN)
    assert voice.spoken == ["Decreasing the volume."]


def test_scroll_up_variant_dispatches_through_real_keyboard_control_handler():
    """"scroll upar" - a brand-new capability (see keyboard_control.
    scroll_up(), the new fixed Page-Up shortcut). Recursion proof: the
    normalizer renders the fixed literal "scroll up", handed back to
    process(), which the PRIMARY dispatch chain (keyboard_control.
    handle()) then recognizes directly - never a direct control-module
    call from the normalizer itself."""
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("keyboard_control.input_control.press_key") as mock_press:
        result = processor.process("scroll upar")

    assert result is True
    mock_press.assert_called_once_with(input_control.VK_PRIOR)
    assert voice.spoken == ["Scrolling up."]


def test_scroll_down_variant_dispatches_through_real_keyboard_control_handler():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("keyboard_control.input_control.press_key") as mock_press:
        result = processor.process("neeche scroll karo")

    assert result is True
    mock_press.assert_called_once_with(input_control.VK_NEXT)
    assert voice.spoken == ["Scrolling down."]


def test_english_scroll_up_now_works_directly_without_the_multilingual_layer():
    """Plain English "scroll up" was a real gap in EVERY existing
    handler before this phase (see keyboard_control.py) - it must now
    be recognized by the PRIMARY dispatch chain alone, with the
    multilingual layer OFF, proving this is a genuine new base
    capability, not something only the Urdu layer can reach."""
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", False), \
         patch("keyboard_control.input_control.press_key") as mock_press:
        result = processor.process("scroll up")

    assert result is True
    mock_press.assert_called_once_with(input_control.VK_PRIOR)


def test_exit_variant_band_ho_jao_dispatches_through_real_safe_exit_path():
    """"band ho jao" must stop the run loop via the exact same safe
    "exit"/"quit" path as the existing English exit words (see
    commands.EXIT_WORDS) - never the dangerous shutdown/restart path,
    proven here by mock_all_real_actions() catching NO real system
    call."""
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         mock_all_real_actions() as mocks:
        result = processor.process("band ho jao")

    assert result is False
    assert "Going offline" in voice.spoken[-1]
    _assert_nothing_but_prompt_happened(mocks)


def test_exit_variant_off_ho_jao_dispatches_through_real_safe_exit_path():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         mock_all_real_actions() as mocks:
        result = processor.process("off ho jao")

    assert result is False
    assert "Going offline" in voice.spoken[-1]
    _assert_nothing_but_prompt_happened(mocks)


def test_band_karo_next_to_a_known_application_never_exits_jarvis():
    """"chrome band karo" must never exit JARVIS. In practice this is
    resolved before the multilingual layer is even reached - web_control
    .handle()'s existing bare "chrome" substring check (part of the
    PRIMARY dispatch chain, checked long before this layer) already
    claims it and opens Chrome, exactly as it would for the bare English
    word "chrome" alone, completely unaffected by this phase. The
    multilingual layer's own "band karo" + known-application guard (see
    multilingual_normalizer.test_band_karo_with_a_known_application_
    name_is_not_exit) is what protects any known-application phrase
    that ISN'T already bare-matched earlier in the chain - this test
    documents the end-to-end outcome, not which layer produced it."""
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("chrome band karo")

    assert result is True
    assert result is not False
    mock_open.assert_called_once_with("https://www.google.com")
    assert voice.spoken == ["Opening Chrome."]


def test_computer_band_karo_still_triggers_dangerous_gate_not_exit():
    """The new bare "band karo" exit marker must never shadow the
    existing dangerous-command confirmation gate for "computer band
    karo" (-> shutdown)."""
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch.object(
             config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
         ), mock_all_real_actions() as mocks:
        result = processor.process("computer band karo")

    assert result is True
    _assert_nothing_but_prompt_happened(mocks)
    assert "sure" in voice.spoken[-1].lower()
    assert "shut down" in voice.spoken[-1].lower()


# =======================================================================
# PHASE 11.7: finish-the-job pass - end-to-end via CommandProcessor.
# process(). Covers: safe targeted "close <app>" (via intent_layer.py's
# new TARGETED_ACTION_SYNONYMS_UR, checked before the multilingual
# layer - and multilingual_normalizer.py's own _check_close_
# application() as a second, independent path when the intent fallback
# layer is off), Urdu-script equivalents, and the documented "bare
# app-name substring match" limitation for chrome/edge/etc.
# =======================================================================

def test_youtube_band_karo_closes_via_intent_layer_synonym_not_exit():
    """The primary, most-likely-reached path in the real default
    configuration (ENABLE_INTENT_FALLBACK_LAYER defaults True and is
    checked before the multilingual layer): intent_layer.py's new
    TARGETED_ACTION_SYNONYMS_UR resolves "youtube band karo" to "close
    youtube", dispatched through the real window_control.
    handle_targeted()."""
    processor, voice = make_processor()

    with patch("window_control.user32.PostMessageW") as mock_post, \
         patch("window_control.user32.GetForegroundWindow", return_value=0), \
         patch(
             "window_control.find_window_by_application", return_value=42
         ):
        result = processor.process("youtube band karo")

    assert result is True
    mock_post.assert_called_once_with(42, window_control.WM_CLOSE, 0, 0)
    assert voice.spoken == ["Closing Youtube."]


def test_youtube_band_karo_never_exits_jarvis():
    processor, voice = make_processor()

    with mock_all_real_actions() as mocks:
        result = processor.process("youtube band karo")

    assert result is True
    assert result is not False
    assert "Going offline" not in "".join(voice.spoken)


def test_chrome_band_karo_documented_limitation_opens_not_closes_but_never_exits():
    """Known, pre-existing, documented limitation (see multilingual_
    normalizer.py's _check_close_application() docstring and the Phase
    11.7 report): "chrome" is bare-substring-matched by web_control.
    handle() - part of the PRIMARY dispatch chain, checked before
    EITHER the intent fallback or multilingual layers - so "chrome band
    karo" opens Chrome rather than closing it. This test documents the
    actual, current, SAFE behavior (never exit, never a dangerous
    action) rather than silently asserting an idealized one."""
    processor, voice = make_processor()

    with patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("chrome band karo")

    assert result is True
    mock_open.assert_called_once_with("https://www.google.com")
    assert voice.spoken == ["Opening Chrome."]


def test_urdu_script_how_are_you_dispatches_through_real_greeting_handler():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True):
        result = processor.process("کیسے ہو")

    assert result is True
    assert "How can I help you" in voice.spoken[-1]


def test_urdu_script_browser_open_dispatches_through_real_web_control_handler():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("براؤزر کھولو")

    assert result is True
    mock_open.assert_called_once_with("https://www.google.com")


def test_urdu_script_scroll_up_dispatches_through_real_keyboard_control_handler():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("keyboard_control.input_control.press_key") as mock_press:
        result = processor.process("اسکرول اوپر")

    assert result is True
    mock_press.assert_called_once_with(input_control.VK_PRIOR)


def test_urdu_script_exit_variant_dispatches_through_real_safe_exit_path():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         mock_all_real_actions() as mocks:
        result = processor.process("بند ہو جاؤ")

    assert result is False
    assert "Going offline" in voice.spoken[-1]
    _assert_nothing_but_prompt_happened(mocks)


def test_urdu_script_computer_band_karo_still_triggers_dangerous_gate():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch.object(
             config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
         ), mock_all_real_actions() as mocks:
        result = processor.process("کمپیوٹر بند کرو")

    assert result is True
    _assert_nothing_but_prompt_happened(mocks)
    assert "sure" in voice.spoken[-1].lower()
    assert "shut down" in voice.spoken[-1].lower()


def test_intensifier_volume_phrase_dispatches_through_real_volume_control_handler():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("volume_control.input_control.press_key") as mock_press:
        result = processor.process("volume thora barha do")

    assert result is True
    mock_press.assert_called_once_with(input_control.VK_VOLUME_UP)


def test_key_dabao_with_key_word_dispatches_through_real_keyboard_control_handler():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("keyboard_control.input_control.press_key") as mock_press:
        result = processor.process("enter key dabao")

    assert result is True
    mock_press.assert_called_once_with(input_control.VK_RETURN)


def test_mixed_time_kya_hai_dispatches_through_real_information_handler():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True):
        result = processor.process("time kya hai")

    assert result is True
    assert "current time is" in voice.spoken[-1].lower()


# =======================================================================
# PHASE 11.2: dangerous-command (lock/shutdown/restart) parity for
# Urdu-script, Roman Urdu, and mixed-language commands - end-to-end via
# CommandProcessor.process(). See multilingual_normalizer.py's
# _check_dangerous()/understand_dangerous() and context_manager.py's
# updated _looks_like_new_command(). Section labels mirror the Phase
# 11.2 test-matrix requirements.
# =======================================================================

# ---- Confirmation OFF (default): a recognized dangerous phrase
# executes immediately, identically to how the exact English phrase
# already behaves - the multilingual layer recognizing a paraphrase
# does not change what happens once the canonical command is produced.

def test_urdu_script_lock_executes_immediately_when_confirmation_off():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("system_control.os.system") as mock_system:
        result = processor.process("کمپیوٹر لاک کرو")

    assert result is True
    mock_system.assert_called_once_with("rundll32.exe user32.dll,LockWorkStation")


def test_roman_urdu_shutdown_executes_immediately_when_confirmation_off():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("system_control.os.system") as mock_system:
        result = processor.process("computer band karo")

    assert result is True
    mock_system.assert_called_once_with("shutdown /s /t 5")


def test_mixed_language_restart_executes_immediately_when_confirmation_off():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("system_control.os.system") as mock_system:
        result = processor.process("کمپیوٹر ko restart karo")

    assert result is True
    mock_system.assert_called_once_with("shutdown /r /t 5")


# ---- D. Phase 9 gate integration: confirmation ON - every multilingual
# dangerous command must reach the existing confirmation gate, and
# nothing executes before confirmation.

def test_urdu_script_lock_requires_confirmation_when_gate_on():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch.object(
             config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
         ), mock_all_real_actions() as mocks:
        result = processor.process("کمپیوٹر لاک کرو")

    assert result is True
    _assert_nothing_but_prompt_happened(mocks)
    assert "sure" in voice.spoken[-1].lower()
    assert "lock" in voice.spoken[-1].lower()
    assert processor._pending_confirmation == "lock computer"


def test_roman_urdu_shutdown_requires_confirmation_when_gate_on():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch.object(
             config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
         ), mock_all_real_actions() as mocks:
        result = processor.process("computer ko band karo")

    assert result is True
    _assert_nothing_but_prompt_happened(mocks)
    assert "sure" in voice.spoken[-1].lower()
    assert "shut down" in voice.spoken[-1].lower()
    assert processor._pending_confirmation == "shutdown computer"


def test_mixed_language_restart_requires_confirmation_when_gate_on():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch.object(
             config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
         ), mock_all_real_actions() as mocks:
        result = processor.process("computer کو restart کرو")

    assert result is True
    _assert_nothing_but_prompt_happened(mocks)
    assert "sure" in voice.spoken[-1].lower()
    assert "restart" in voice.spoken[-1].lower()
    assert processor._pending_confirmation == "restart computer"


# ---- E. Confirmation rejection: dangerous action NOT executed.

def test_urdu_dangerous_command_confirmation_rejected_does_not_execute():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch.object(
             config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
         ), mock_all_real_actions() as mocks:
        processor.process("computer band karo")
        result = processor.process("no")

    assert result is True
    _assert_nothing_but_prompt_happened(mocks)
    assert voice.spoken[-1] == "Cancelled."
    assert processor._pending_confirmation is None


# ---- F. Confirmation acceptance: existing (mocked) execution path
# reached, for each of lock/shutdown/restart.

def test_urdu_lock_confirmation_accepted_executes_via_existing_path():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch.object(
             config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
         ), patch("system_control.os.system") as mock_system:
        processor.process("کمپیوٹر لاک کرو")
        result = processor.process("yes")

    assert result is True
    mock_system.assert_called_once_with("rundll32.exe user32.dll,LockWorkStation")


def test_roman_urdu_shutdown_confirmation_accepted_executes_via_existing_path():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch.object(
             config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
         ), patch("system_control.os.system") as mock_system:
        processor.process("computer band karo")
        result = processor.process("confirm")

    assert result is True
    mock_system.assert_called_once_with("shutdown /s /t 5")


def test_mixed_language_restart_confirmation_accepted_executes_via_existing_path():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch.object(
             config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
         ), patch("system_control.os.system") as mock_system:
        processor.process("کمپیوٹر shutdown کرو")
        result = processor.process("yes")

    assert result is True
    mock_system.assert_called_once_with("shutdown /s /t 5")


# ---- G/H. Context / pending-slot safety: a dangerous multilingual
# reply to "What should I search for?" must be diverted into the Phase
# 9 gate, never poured into the search query. Covers lock, shutdown,
# restart, Urdu script, Roman Urdu, and the mixed-language forms named
# explicitly in the Phase 11.2 spec ("computer ko lock karo", "computer
# کو lock کرو", "کمپیوٹر ko restart karo", "کمپیوٹر shutdown کرو").

DANGEROUS_CONTEXT_DIVERSION_CASES = (
    ("computer lock karo", "lock computer"),
    ("computer ko lock karo", "lock computer"),
    ("کمپیوٹر لاک کرو", "lock computer"),
    ("کمپیوٹر کو لاک کرو", "lock computer"),
    ("computer کو lock کرو", "lock computer"),
    ("computer band karo", "shutdown computer"),
    ("computer ko band karo", "shutdown computer"),
    ("کمپیوٹر بند کرو", "shutdown computer"),
    ("کمپیوٹر shutdown کرو", "shutdown computer"),
    ("computer restart karo", "restart computer"),
    ("computer ko restart karo", "restart computer"),
    ("کمپیوٹر ری اسٹارٹ کرو", "restart computer"),
    ("کمپیوٹر ko restart karo", "restart computer"),
)


def test_pending_search_slot_dangerous_reply_is_diverted_not_swallowed_as_search():
    """"What should I search for?" -> a dangerous multilingual reply
    must never become that literal search query - it must be recognized
    as a new dangerous command and flow into the existing Phase 9
    confirmation gate instead."""

    for reply, expected_dangerous_phrase in DANGEROUS_CONTEXT_DIVERSION_CASES:

        processor, voice = make_processor()

        with patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
             patch.object(config, "ENABLE_CONTEXT_LAYER", True), \
             patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True):
            processor.process("search youtube")

        assert voice.spoken[-1] == "What should I search for?", reply

        with patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
             patch.object(config, "ENABLE_CONTEXT_LAYER", True), \
             patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
             patch.object(
                 config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
             ), mock_all_real_actions() as mocks:
            result = processor.process(reply)

        assert result is True, reply
        _assert_nothing_but_prompt_happened(mocks)
        assert "sure" in voice.spoken[-1].lower(), reply
        assert processor._pending_confirmation == expected_dangerous_phrase, reply
        assert not any("Searching for" in spoken for spoken in voice.spoken), reply
        assert processor._pending_slot is None, reply


def test_pending_search_slot_dangerous_reply_diversion_without_confirmation_gate():
    """Same diversion proof, with REQUIRE_CONFIRMATION_FOR_DANGEROUS_
    COMMANDS at its default (False) - the dangerous command still must
    not become a search query; it executes immediately instead, exactly
    like the equivalent bare dangerous phrase already would."""

    processor, voice = make_processor()

    with patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
         patch.object(config, "ENABLE_CONTEXT_LAYER", True), \
         patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True):
        processor.process("search youtube")

    assert voice.spoken[-1] == "What should I search for?"

    with patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
         patch.object(config, "ENABLE_CONTEXT_LAYER", True), \
         patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("system_control.os.system") as mock_system, \
         patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("computer lock karo")

    assert result is True
    mock_system.assert_called_once_with("rundll32.exe user32.dll,LockWorkStation")
    mock_open.assert_not_called()


# ---- J. Recursive process() proof: raw multilingual command -> canonical
# dangerous command -> second process() invocation -> Phase 9 gate.

def test_dangerous_multilingual_command_recurses_through_process_and_reaches_gate():
    processor, voice = make_processor()

    real_process = processor.process
    seen_commands = []

    def spy_process(command):
        seen_commands.append(command)
        return real_process(command)

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch.object(
             config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
         ), patch.object(processor, "process", side_effect=spy_process), \
         patch("system_control.os.system") as mock_system:
        result = processor.process("کمپیوٹر لاک کرو")

    assert result is True
    assert seen_commands == ["کمپیوٹر لاک کرو", "lock computer"]
    mock_system.assert_not_called()
    assert processor._pending_confirmation == "lock computer"
    assert "sure" in voice.spoken[-1].lower()


def test_dangerous_multilingual_command_recursion_with_confirmation_off_still_single_hop():
    """Even with confirmation off (immediate execution), the canonical
    command is still produced via exactly one recursive process() call
    - never executed directly from within the multilingual-layer branch
    itself."""

    processor, voice = make_processor()

    real_process = processor.process
    seen_commands = []

    def spy_process(command):
        seen_commands.append(command)
        return real_process(command)

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch.object(processor, "process", side_effect=spy_process), \
         patch("system_control.os.system") as mock_system:
        result = processor.process("computer band karo")

    assert result is True
    assert seen_commands == ["computer band karo", "shutdown computer"]
    mock_system.assert_called_once_with("shutdown /s /t 5")


# ---- K. Dangerous substring defense: a legitimate search containing
# dangerous-sounding words must remain a search unless the raw command
# itself matches the explicit dangerous-command recognition rules.

def test_search_containing_dangerous_words_remains_a_search_not_a_dangerous_command():
    """Explicit Phase 11.2 spec example: "search for words computer
    lock karo" is plain ENGLISH text starting with "search for", so it
    is handled entirely by the existing, pre-Phase-11 web_control.
    handle() dispatch before this layer is ever reached - completely
    unaffected by Phase 11.2. The Phase 9 raw-text gate only matches
    the exact "lock computer"/"shutdown computer"/"restart computer"
    substrings (noun AFTER the verb) - "computer lock karo" (noun
    BEFORE the verb) does not match that order, so the gate does not
    fire either."""

    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("web_control.webbrowser.open") as mock_open, \
         patch("system_control.subprocess.Popen") as mock_popen, \
         patch("system_control.os.system") as mock_system:
        result = processor.process("search for words computer lock karo")

    assert result is True
    mock_open.assert_called_once_with(
        "https://www.google.com/search?q=words+computer+lock+karo"
    )
    mock_popen.assert_not_called()
    mock_system.assert_not_called()


def test_urdu_search_containing_action_word_without_noun_remains_a_search():
    """The multilingual-layer equivalent of the case above: an Urdu-
    script phrase containing a dangerous ACTION+VERB marker ("لاک کرو")
    but no "computer"/"کمپیوٹر" noun must remain an ordinary search,
    never a dangerous command."""

    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("web_control.webbrowser.open") as mock_open, \
         patch("system_control.os.system") as mock_system:
        result = processor.process("لاک کرو تلاش کرو")

    assert result is True
    mock_open.assert_called_once_with("https://www.google.com/search?q=لاک+کرو")
    mock_system.assert_not_called()


def test_chrome_close_mixed_language_is_never_treated_as_shutdown():
    """"chrome بند کرو" ("close chrome") is explicitly listed in the
    Phase 11.2 spec as a mixed-language form that must NOT be treated
    as a shutdown command. In practice, "chrome" is already bare-
    substring-matched by the pre-existing English web_control.handle()
    dispatch before this layer is ever reached (the same characteristic
    already documented in the Phase 11.1 report) - so it opens Chrome,
    not closes it - but the safety property under test here holds
    either way: os.system (the dangerous-command primitive) must never
    be called for this phrase."""

    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         mock_all_real_actions() as mocks:
        result = processor.process("chrome بند کرو")

    assert result is True
    mocks["os_system"].assert_not_called()


# ---- L. Context expiration/regression: Phase 10.3-10.5 behavior is
# unaffected by Phase 11.2, including when the multilingual layer is
# ALSO enabled at the same time.

def test_reference_resolution_still_works_with_multilingual_layer_also_enabled():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         mock_all_real_actions() as mocks, \
         patch("web_control.webbrowser.open"), \
         patch("web_control.os.path.exists", return_value=False):
        processor.process("open chrome")
        result = processor.process("close it")

    assert result is True
    assert voice.spoken[-2] == "Opening Chrome."
    assert voice.spoken[-1] == "Closing Chrome."
    mocks["os_system"].assert_not_called()


def test_repeat_search_still_works_with_multilingual_layer_also_enabled():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("web_control.webbrowser.open") as mock_open:
        processor.process("search for cats")
        result = processor.process("search that again")

    assert result is True
    assert mock_open.call_count == 2


# =======================================================================
# LIVE-VOICE-TEST FOLLOW-UP: expanded keyboard/mouse/browser vocabulary,
# plus the tab-management precedence fix.
#
# Root cause of the "open new tab" -> "Pressing Tab." / "tab band karo"
# -> "Pressing Tab." bugs: intent_layer.KEY_WORD_PATTERNS["tab"] bare-
# word-matched "tab" ANYWHERE in the text (see intent_layer.py's PRESS_
# KEY rescue), with no requirement that it appear in a "press"-like
# context - so any phrase merely containing the standalone word "tab"
# was rewritten to "press tab" and re-dispatched. Fixed by (1) adding
# real NEW_TAB/CLOSE_TAB/NEXT_TAB/PREVIOUS_TAB recognition to web_
# control.handle() (PRIMARY dispatch chain, checked well before intent_
# layer's fallback ever runs, so English phrasings never reach the bare
# "tab" rescue at all) and (2) excluding tab-management phrases from
# intent_layer's bare "tab" rescue directly (see intent_layer.
# TAB_MANAGEMENT_MARKERS), so the Roman-Urdu forms fall through
# undisturbed to multilingual_normalizer._check_tab_browser() instead.
# =======================================================================

# ---- Scroll: new Roman-Urdu "niche" spelling variant ----

def test_scroll_niche_dispatches_scroll_down():
    processor, voice = make_processor()

    with patch("keyboard_control.input_control.press_key") as mock_press:
        result = processor.process("scroll niche")

    assert result is True
    mock_press.assert_called_once_with(input_control.VK_NEXT)
    assert voice.spoken == ["Scrolling down."]


# ---- Keyboard: backspace, modifier combos ----

def test_press_backspace_command():
    processor, voice = make_processor()

    with patch("keyboard_control.input_control.press_key") as mock_press:
        result = processor.process("press backspace")

    assert result is True
    mock_press.assert_called_once_with(input_control.VK_BACK)
    assert voice.spoken == ["Pressing Backspace."]


def test_press_back_space_two_words_normalizes_to_backspace():
    processor, voice = make_processor()

    with patch("keyboard_control.input_control.press_key") as mock_press:
        result = processor.process("press back space")

    assert result is True
    mock_press.assert_called_once_with(input_control.VK_BACK)


def test_press_delete_remains_unrecognized():
    """Deliberate, preserved security decision (see keyboard_control.
    handle()'s own docstring and tests/test_security.py's test_press_
    unknown_key_is_not_sent_to_keyboard): Delete is the one key this
    project never adds, since an unconfirmed Delete keypress can
    destructively delete a selected file/text with no undo prompt."""
    processor, voice = make_processor()

    with patch("keyboard_control.input_control.press_key") as mock_press:
        result = processor.process("press delete")

    assert result is True
    mock_press.assert_not_called()
    assert "don't know how to do that" in voice.spoken[-1]


def test_press_ctrl_c_command():
    processor, voice = make_processor()

    with patch("keyboard_control.input_control.press_key_combo") as mock_combo:
        result = processor.process("press ctrl c")

    assert result is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_C
    )
    assert voice.spoken == ["Copying."]


def test_press_control_c_normalizes_to_ctrl_c():
    processor, voice = make_processor()

    with patch("keyboard_control.input_control.press_key_combo") as mock_combo:
        result = processor.process("press control c")

    assert result is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_C
    )


def test_press_control_v_command():
    processor, voice = make_processor()

    with patch("keyboard_control.input_control.press_key_combo") as mock_combo:
        result = processor.process("press control v")

    assert result is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_V
    )
    assert voice.spoken == ["Pasting."]


def test_press_ctrl_x_command_cuts():
    processor, voice = make_processor()

    with patch("keyboard_control.input_control.press_key_combo") as mock_combo:
        result = processor.process("press ctrl x")

    assert result is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_X
    )
    assert voice.spoken == ["Cutting."]


def test_press_control_a_command():
    processor, voice = make_processor()

    with patch("keyboard_control.input_control.press_key_combo") as mock_combo:
        result = processor.process("press control a")

    assert result is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_A
    )
    assert voice.spoken == ["Selecting all."]


def test_press_control_z_command():
    processor, voice = make_processor()

    with patch("keyboard_control.input_control.press_key_combo") as mock_combo:
        result = processor.process("press control z")

    assert result is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_Z
    )
    assert voice.spoken == ["Undoing."]


def test_press_alt_tab_command():
    processor, voice = make_processor()

    with patch("keyboard_control.input_control.press_key_combo") as mock_combo, \
         patch("keyboard_control.input_control.press_key") as mock_press:
        result = processor.process("press alt tab")

    assert result is True
    mock_press.assert_not_called()
    mock_combo.assert_called_once_with(
        input_control.VK_MENU, input_control.VK_TAB
    )


def test_press_control_shift_escape_command():
    processor, voice = make_processor()

    with patch("keyboard_control.input_control.press_key_combo") as mock_combo:
        result = processor.process("press control shift escape")

    assert result is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_SHIFT, input_control.VK_ESCAPE
    )


def test_press_esc_normalizes_to_escape():
    processor, voice = make_processor()

    with patch("keyboard_control.input_control.press_key") as mock_press:
        result = processor.process("press esc")

    assert result is True
    mock_press.assert_called_once_with(input_control.VK_ESCAPE)
    assert voice.spoken == ["Pressing Escape."]


# ---- Mouse ----

def test_click_command():
    processor, voice = make_processor()

    with patch("mouse_control.input_control.click_mouse") as mock_click:
        result = processor.process("click")

    assert result is True
    mock_click.assert_called_once_with()
    assert voice.spoken == ["Clicking."]


def test_left_click_command():
    processor, voice = make_processor()

    with patch("mouse_control.input_control.click_mouse") as mock_click:
        result = processor.process("left click")

    assert result is True
    mock_click.assert_called_once_with()


def test_double_click_command():
    processor, voice = make_processor()

    with patch("mouse_control.input_control.click_mouse") as mock_click:
        result = processor.process("double click")

    assert result is True
    assert mock_click.call_count == 2
    assert voice.spoken == ["Double clicking."]


def test_right_click_command():
    processor, voice = make_processor()

    with patch("mouse_control.input_control.right_click_mouse") as mock_right:
        result = processor.process("right click")

    assert result is True
    mock_right.assert_called_once_with()
    assert voice.spoken == ["Right clicking."]


def test_move_left_command():
    processor, voice = make_processor()

    with patch("mouse_control.input_control.move_mouse_by") as mock_move:
        result = processor.process("move left")

    assert result is True
    mock_move.assert_called_once_with(-mouse_control.MOVE_STEP_PIXELS, 0)


def test_move_right_command():
    processor, voice = make_processor()

    with patch("mouse_control.input_control.move_mouse_by") as mock_move:
        result = processor.process("move right")

    assert result is True
    mock_move.assert_called_once_with(mouse_control.MOVE_STEP_PIXELS, 0)


def test_move_up_command():
    processor, voice = make_processor()

    with patch("mouse_control.input_control.move_mouse_by") as mock_move:
        result = processor.process("move up")

    assert result is True
    mock_move.assert_called_once_with(0, -mouse_control.MOVE_STEP_PIXELS)


def test_move_down_command():
    processor, voice = make_processor()

    with patch("mouse_control.input_control.move_mouse_by") as mock_move:
        result = processor.process("move down")

    assert result is True
    mock_move.assert_called_once_with(0, mouse_control.MOVE_STEP_PIXELS)


# ---- Browser: refresh/reload ----

def test_refresh_command():
    processor, voice = make_processor()

    with patch("web_control.input_control.press_key") as mock_press:
        result = processor.process("refresh")

    assert result is True
    mock_press.assert_called_once_with(input_control.VK_F5)
    assert voice.spoken == ["Refreshing."]


def test_reload_command():
    processor, voice = make_processor()

    with patch("web_control.input_control.press_key") as mock_press:
        result = processor.process("reload")

    assert result is True
    mock_press.assert_called_once_with(input_control.VK_F5)


# ---- Browser tab management: precedence over PRESS_TAB (the exact
# live-test bug) ----

def test_open_new_tab_is_new_tab_not_press_tab():
    processor, voice = make_processor()

    with patch("web_control.input_control.press_key_combo") as mock_web_combo, \
         patch("keyboard_control.input_control.press_key") as mock_key_press:
        result = processor.process("open new tab")

    assert result is True
    mock_key_press.assert_not_called()
    mock_web_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_T
    )
    assert voice.spoken == ["Opening new tab."]


def test_new_tab_is_new_tab_not_press_tab():
    processor, voice = make_processor()

    with patch("web_control.input_control.press_key_combo") as mock_web_combo, \
         patch("keyboard_control.input_control.press_key") as mock_key_press:
        result = processor.process("new tab")

    assert result is True
    mock_key_press.assert_not_called()
    mock_web_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_T
    )


def test_close_tab_command():
    processor, voice = make_processor()

    with patch("web_control.input_control.press_key_combo") as mock_combo:
        result = processor.process("close tab")

    assert result is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_W
    )
    assert voice.spoken == ["Closing tab."]


def test_next_tab_is_next_tab_not_press_tab():
    processor, voice = make_processor()

    with patch("web_control.input_control.press_key_combo") as mock_web_combo, \
         patch("keyboard_control.input_control.press_key") as mock_key_press:
        result = processor.process("next tab")

    assert result is True
    mock_key_press.assert_not_called()
    mock_web_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_TAB
    )


def test_previous_tab_is_previous_tab_not_press_tab():
    processor, voice = make_processor()

    with patch("web_control.input_control.press_key_combo") as mock_web_combo, \
         patch("keyboard_control.input_control.press_key") as mock_key_press:
        result = processor.process("previous tab")

    assert result is True
    mock_key_press.assert_not_called()
    mock_web_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_SHIFT, input_control.VK_TAB
    )


def test_press_tab_still_works():
    """Regression guard: the new tab-management commands must never
    shadow the pre-existing, unrelated "press tab" command."""
    processor, voice = make_processor()

    with patch("keyboard_control.input_control.press_key") as mock_press:
        result = processor.process("press tab")

    assert result is True
    mock_press.assert_called_once_with(input_control.VK_TAB)
    assert voice.spoken == ["Pressing Tab."]


def test_tab_band_karo_is_close_tab_not_press_tab_or_exit():
    """The exact live-test bug, Roman-Urdu form. Also proves it's never
    misrouted to EXIT: "tab band karo" contains the generic
    _AMBIGUOUS_EXIT_MARKERS phrase "band karo" (see multilingual_
    normalizer._check_tab_browser()'s own docstring)."""
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("web_control.input_control.press_key_combo") as mock_web_combo, \
         patch("keyboard_control.input_control.press_key") as mock_key_press:
        result = processor.process("tab band karo")

    assert result is True
    assert result is not False  # never the EXIT path
    mock_key_press.assert_not_called()
    mock_web_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_W
    )
    assert voice.spoken == ["Closing tab."]


def test_naya_tab_kholo_is_new_tab():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("web_control.input_control.press_key_combo") as mock_combo:
        result = processor.process("naya tab kholo")

    assert result is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_T
    )


# ---- Browser navigation: go back/forward, refresh (Roman-Urdu) ----

def test_wapas_jao_is_go_back():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("web_control.input_control.press_key_combo") as mock_combo:
        result = processor.process("wapas jao")

    assert result is True
    mock_combo.assert_called_once_with(
        input_control.VK_MENU, input_control.VK_LEFT
    )
    assert voice.spoken == ["Going back."]


def test_aagay_jao_is_go_forward():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("web_control.input_control.press_key_combo") as mock_combo:
        result = processor.process("aagay jao")

    assert result is True
    mock_combo.assert_called_once_with(
        input_control.VK_MENU, input_control.VK_RIGHT
    )
    assert voice.spoken == ["Going forward."]


def test_refresh_karo_is_refresh():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("web_control.input_control.press_key") as mock_press:
        result = processor.process("refresh karo")

    assert result is True
    mock_press.assert_called_once_with(input_control.VK_F5)


def test_press_backspace_not_treated_as_go_back():
    """Regression guard: "backspace" contains "back" as a literal
    substring (backspace = "back" + "space") - a bare `"back" in
    command` check in web_control.handle() would incorrectly hijack
    "press backspace" into the browser "go back" action instead of the
    Backspace key. See web_control._BACK_PATTERN's own comment."""
    processor, voice = make_processor()

    with patch("web_control.input_control.press_key_combo") as mock_web_combo, \
         patch("keyboard_control.input_control.press_key") as mock_key_press:
        result = processor.process("press backspace")

    assert result is True
    mock_web_combo.assert_not_called()
    mock_key_press.assert_called_once_with(input_control.VK_BACK)


# ---- Case-insensitivity / whitespace variations ----

def test_double_click_case_insensitive_and_extra_whitespace():
    processor, voice = make_processor()

    with patch("mouse_control.input_control.click_mouse") as mock_click:
        result = processor.process("  Double   Click  ")

    assert result is True
    assert mock_click.call_count == 2


def test_new_tab_case_insensitive():
    processor, voice = make_processor()

    with patch("web_control.input_control.press_key_combo") as mock_combo:
        result = processor.process("Open New Tab")

    assert result is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_T
    )


# =======================================================================
# ACTION-EXECUTION FOLLOW-UP: SendInput reliability + honest success
# reporting + "open a new chrome tab" precedence.
# =======================================================================

def test_open_a_new_chrome_tab_is_new_tab_not_open_chrome():
    """The exact live-test regression report: "jarvis open a new chrome
    tab" previously produced "Opening Chrome." (the bare "chrome"
    fallback in web_control.handle()) because "new tab" is not a
    contiguous substring of "open a new chrome tab" - "chrome" sits
    between "new" and "tab". Must now resolve to NEW_TAB and never
    launch/open a browser at all."""
    processor, voice = make_processor()

    with patch("web_control.input_control.press_key_combo") as mock_combo, \
         patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open") as mock_open, \
         patch("web_control.subprocess.Popen") as mock_popen:
        result = processor.process("open a new chrome tab")

    assert result is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_T
    )
    mock_open.assert_not_called()
    mock_popen.assert_not_called()
    assert voice.spoken == ["Opening new tab."]


def test_new_tab_reports_failure_when_input_injection_is_rejected():
    """Root-cause fix: the action executor must not claim success when
    the low-level SendInput call was actually rejected by the OS
    (e.g. blocked by UIPI) - this is what let JARVIS say "Opening new
    tab." with no visible effect."""
    processor, voice = make_processor()

    with patch("web_control.input_control.press_key_combo", return_value=False):
        result = processor.process("new tab")

    assert result is True
    assert voice.spoken == [web_control.INPUT_FAILURE_MESSAGE]


def test_next_tab_reports_failure_when_input_injection_is_rejected():
    processor, voice = make_processor()

    with patch("web_control.input_control.press_key_combo", return_value=False):
        result = processor.process("next tab")

    assert result is True
    assert voice.spoken == [web_control.INPUT_FAILURE_MESSAGE]


def test_new_tab_still_reports_success_on_a_healthy_injection():
    """Regression guard alongside the two failure tests above: a
    successful injection must still produce the normal, unchanged
    spoken confirmation."""
    processor, voice = make_processor()

    with patch("web_control.input_control.press_key_combo", return_value=True):
        result = processor.process("new tab")

    assert result is True
    assert voice.spoken == ["Opening new tab."]


# =======================================================================
# PHASE 11.12: natural-language precedence hardening + Roman-Urdu
# navigation aliases (live-test follow-up).
#
# Live bugs fixed here:
#   1. "jarvis close the tab" -> "Pressing Tab." (web_control had no
#      CLOSE_TAB recognition at all for anything but the exact,
#      article-free "close tab", so it fell all the way through to
#      intent_layer's bare "tab" PRESS_KEY rescue.)
#   2. "jarvis close the new tab" -> "Opening new tab." (NEW_TAB_ALIASES
#      matched the literal substring "new tab" inside the phrase before
#      any CLOSE_TAB check existed at all.)
#   3. "jarvis aage jao" was not recognized (missing Roman-Urdu spelling
#      variant of "aagay jao").
# See web_control.CLOSE_TAB_RE and multilingual_normalizer.GO_FORWARD_
# MARKERS/GO_BACK_MARKERS for the fixes.
# =======================================================================

# ---- Bug 1 + 2: CLOSE_TAB precedence, end-to-end ----

def test_close_the_tab_is_close_tab_not_press_tab():
    processor, voice = make_processor()

    with patch("web_control.input_control.press_key_combo") as mock_web_combo, \
         patch("keyboard_control.input_control.press_key") as mock_key_press:
        result = processor.process("close the tab")

    assert result is True
    mock_key_press.assert_not_called()
    mock_web_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_W
    )
    assert voice.spoken == ["Closing tab."]


def test_close_this_tab_is_close_tab():
    processor, voice = make_processor()

    with patch("web_control.input_control.press_key_combo") as mock_web_combo:
        result = processor.process("close this tab")

    assert result is True
    mock_web_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_W
    )


def test_close_the_new_tab_is_close_tab_not_new_tab():
    processor, voice = make_processor()

    with patch("web_control.input_control.press_key_combo") as mock_web_combo:
        result = processor.process("close the new tab")

    assert result is True
    mock_web_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_W
    )
    assert voice.spoken == ["Closing tab."]


def test_tab_band_karo_still_resolves_to_close_tab_after_precedence_fix():
    """Regression: the Phase 11.12 CLOSE_TAB_RE change must not affect
    the pre-existing Roman-Urdu path at all."""
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("web_control.input_control.press_key_combo") as mock_web_combo:
        result = processor.process("tab band karo")

    assert result is True
    mock_web_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_W
    )


def test_tab_band_kar_do_resolves_to_close_tab():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("web_control.input_control.press_key_combo") as mock_web_combo:
        result = processor.process("tab band kar do")

    assert result is True
    mock_web_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_W
    )


# ---- Bug 3 + new aliases: Roman-Urdu GO_FORWARD/GO_BACK, end-to-end ----

def test_aage_jao_is_go_forward():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("web_control.input_control.press_key_combo") as mock_combo:
        result = processor.process("aage jao")

    assert result is True
    mock_combo.assert_called_once_with(
        input_control.VK_MENU, input_control.VK_RIGHT
    )
    assert voice.spoken == ["Going forward."]


def test_agay_jao_is_go_forward():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("web_control.input_control.press_key_combo") as mock_combo:
        result = processor.process("agay jao")

    assert result is True
    mock_combo.assert_called_once_with(
        input_control.VK_MENU, input_control.VK_RIGHT
    )


def test_aglay_page_par_jao_is_go_forward():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("web_control.input_control.press_key_combo") as mock_combo:
        result = processor.process("aglay page par jao")

    assert result is True
    mock_combo.assert_called_once_with(
        input_control.VK_MENU, input_control.VK_RIGHT
    )


def test_wapas_jao_still_is_go_back_after_alias_additions():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("web_control.input_control.press_key_combo") as mock_combo:
        result = processor.process("wapas jao")

    assert result is True
    mock_combo.assert_called_once_with(
        input_control.VK_MENU, input_control.VK_LEFT
    )


def test_peeche_jao_is_go_back():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("web_control.input_control.press_key_combo") as mock_combo:
        result = processor.process("peeche jao")

    assert result is True
    mock_combo.assert_called_once_with(
        input_control.VK_MENU, input_control.VK_LEFT
    )
    assert voice.spoken == ["Going back."]


def test_peechay_jao_is_go_back():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("web_control.input_control.press_key_combo") as mock_combo:
        result = processor.process("peechay jao")

    assert result is True
    mock_combo.assert_called_once_with(
        input_control.VK_MENU, input_control.VK_LEFT
    )


def test_new_tab_kholo_is_new_tab():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("web_control.input_control.press_key_combo") as mock_combo:
        result = processor.process("new tab kholo")

    assert result is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_T
    )


# ---- Negative cases: generic PRESS_TAB/NEW_TAB must never steal a
# more specific command (task's explicit "!= " requirements) ----

def test_close_the_tab_result_is_not_pressing_tab_message():
    processor, voice = make_processor()

    with patch("web_control.input_control.press_key_combo", return_value=True), \
         patch("keyboard_control.input_control.press_key") as mock_press:
        processor.process("close the tab")

    mock_press.assert_not_called()
    assert "Pressing Tab." not in voice.spoken


def test_close_the_new_tab_result_is_not_opening_new_tab_message():
    processor, voice = make_processor()

    with patch("web_control.input_control.press_key_combo", return_value=True):
        processor.process("close the new tab")

    assert "Opening new tab." not in voice.spoken


def test_open_a_new_tab_is_not_pressing_tab():
    processor, voice = make_processor()

    with patch("web_control.input_control.press_key_combo", return_value=True), \
         patch("keyboard_control.input_control.press_key") as mock_press:
        result = processor.process("open a new tab")

    assert result is True
    mock_press.assert_not_called()
    assert "Pressing Tab." not in voice.spoken


def test_next_tab_is_not_pressing_tab():
    processor, voice = make_processor()

    with patch("web_control.input_control.press_key_combo", return_value=True), \
         patch("keyboard_control.input_control.press_key") as mock_press:
        processor.process("next tab")

    mock_press.assert_not_called()


def test_previous_tab_is_not_pressing_tab():
    processor, voice = make_processor()

    with patch("web_control.input_control.press_key_combo", return_value=True), \
         patch("keyboard_control.input_control.press_key") as mock_press:
        processor.process("previous tab")

    mock_press.assert_not_called()


# ---- Case-insensitivity / whitespace for the new phrases ----

def test_close_the_tab_case_insensitive_and_whitespace():
    processor, voice = make_processor()

    with patch("web_control.input_control.press_key_combo") as mock_combo:
        result = processor.process("  Close   The   Tab  ")

    assert result is True
    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_W
    )


# ---- Safety: dangerous-command gate and the blocked Delete key must
# remain completely untouched by this phase's normalization changes ----

def test_lock_computer_unaffected_by_phase_11_12_changes():
    processor, voice = make_processor()

    with patch.object(
        config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
    ), patch("system_control.os.system") as mock_system:
        result = processor.process("lock computer")

    assert result is True
    mock_system.assert_not_called()
    assert "sure" in voice.spoken[-1].lower()


def test_press_delete_still_unrecognized_after_phase_11_12():
    processor, voice = make_processor()

    with patch("keyboard_control.input_control.press_key") as mock_press:
        result = processor.process("press delete")

    assert result is True
    mock_press.assert_not_called()
    assert "don't know how to do that" in voice.spoken[-1]


# =======================================================================
# PHASE 11.12 (round 2): "closed tab" past-tense STT variant + bare
# Roman-Urdu "tab band" - live-test follow-up.
# =======================================================================

def test_closed_tab_is_close_tab_not_press_tab():
    processor, voice = make_processor()

    with patch("web_control.input_control.press_key_combo") as mock_web_combo, \
         patch("keyboard_control.input_control.press_key") as mock_key_press:
        result = processor.process("closed tab")

    assert result is True
    mock_key_press.assert_not_called()
    mock_web_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_W
    )
    assert voice.spoken == ["Closing tab."]


def test_closed_tab_result_is_not_pressing_tab_message():
    processor, voice = make_processor()

    with patch("web_control.input_control.press_key_combo", return_value=True):
        processor.process("closed tab")

    assert "Pressing Tab." not in voice.spoken


def test_closed_the_tab_is_close_tab():
    processor, voice = make_processor()

    with patch("web_control.input_control.press_key_combo") as mock_web_combo:
        result = processor.process("closed the tab")

    assert result is True
    mock_web_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_W
    )


def test_tab_band_bare_is_close_tab():
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("web_control.input_control.press_key_combo") as mock_web_combo, \
         patch("keyboard_control.input_control.press_key") as mock_key_press:
        result = processor.process("tab band")

    assert result is True
    mock_key_press.assert_not_called()
    mock_web_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_W
    )
    assert voice.spoken == ["Closing tab."]


# ---- Full precedence sweep (task's explicit "!=" requirements) ----

def test_precedence_close_the_tab_is_never_press_tab():
    processor, voice = make_processor()

    with patch("web_control.input_control.press_key_combo", return_value=True), \
         patch("keyboard_control.input_control.press_key") as mock_press:
        processor.process("close the tab")

    mock_press.assert_not_called()


def test_precedence_closed_tab_is_never_press_tab():
    processor, voice = make_processor()

    with patch("web_control.input_control.press_key_combo", return_value=True), \
         patch("keyboard_control.input_control.press_key") as mock_press:
        processor.process("closed tab")

    mock_press.assert_not_called()


def test_precedence_close_the_new_tab_is_never_new_tab():
    """Must resolve to CLOSE_TAB (Ctrl+W), never NEW_TAB (Ctrl+T)."""
    processor, voice = make_processor()

    with patch("web_control.input_control.press_key_combo") as mock_combo:
        processor.process("close the new tab")

    mock_combo.assert_called_once_with(
        input_control.VK_CONTROL, input_control.VK_KEY_W
    )


def test_precedence_open_a_new_tab_is_never_press_tab():
    processor, voice = make_processor()

    with patch("web_control.input_control.press_key_combo", return_value=True), \
         patch("keyboard_control.input_control.press_key") as mock_press:
        processor.process("open a new tab")

    mock_press.assert_not_called()


def test_precedence_next_tab_is_never_press_tab():
    processor, voice = make_processor()

    with patch("web_control.input_control.press_key_combo", return_value=True), \
         patch("keyboard_control.input_control.press_key") as mock_press:
        processor.process("next tab")

    mock_press.assert_not_called()


def test_precedence_previous_tab_is_never_press_tab():
    processor, voice = make_processor()

    with patch("web_control.input_control.press_key_combo", return_value=True), \
         patch("keyboard_control.input_control.press_key") as mock_press:
        processor.process("previous tab")

    mock_press.assert_not_called()


# ---- Negative/ambiguous-command sweep: the new alias/precedence
# changes must not misclassify unrelated commands ----

def test_enclosed_word_does_not_trigger_close_tab():
    """"enclosed" must not word-boundary-match the widened "closed?"
    verb pattern - CLOSE_TAB (Ctrl+W) must never fire for this phrase.
    (The phrase still legitimately contains the standalone word "tab",
    so it may still resolve through the PRE-EXISTING, unrelated bare-
    "tab" PRESS_KEY rescue - that broader behavior is not in this
    phase's scope; only the CLOSE_TAB false-positive is.)"""
    processor, voice = make_processor()

    with patch("web_control.input_control.press_key_combo") as mock_combo:
        processor.process("the enclosed tab is fine")

    mock_combo.assert_not_called()


def test_band_alone_does_not_trigger_close_tab():
    """Bare "band" (no "tab", no "karo") must not be mistaken for
    "tab band" - CLOSE_TAB_MARKERS only matches the full two-word
    phrase, never the generic helper word alone."""
    processor, voice = make_processor()

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch("web_control.input_control.press_key_combo") as mock_combo:
        result = processor.process("band")

    mock_combo.assert_not_called()


def test_open_chrome_unaffected_by_closed_tab_regex():
    """Regression guard: the widened "closed?" verb pattern must not
    affect ordinary Chrome-opening commands."""
    processor, voice = make_processor()

    with patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("open chrome")

    assert result is True
    mock_open.assert_called_once_with("https://www.google.com")
    assert voice.spoken == ["Opening Chrome."]
