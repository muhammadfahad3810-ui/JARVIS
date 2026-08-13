import contextlib
from unittest.mock import patch

import commands
import config
import media_control
import volume_control
import keyboard_control
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
    """Pre-existing (Phase 5) non-match, unrelated to and unchanged by
    Phase 9: 'shut down the computer' has never been recognized as the
    canonical 'shutdown computer' phrase (different words/spacing) -
    confirmation mode does not change this, it only gates phrases that
    were already recognized."""

    processor, voice = make_processor()

    with patch.object(
        config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
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
    mocks["web_open"].assert_not_called()
