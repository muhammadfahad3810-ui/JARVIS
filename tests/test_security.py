"""Phase 5 security/regression tests.

These prove the safety properties the project has maintained since
Phase 3 still hold after adding natural-language understanding:

- JARVIS never passes spoken text as an argument to subprocess.Popen or
  os.system - every Popen/os.system call anywhere in this codebase uses
  a hardcoded argument list. Even when a dangerous-sounding phrase
  superficially matches a known trigger word, the actual subprocess
  call never includes anything derived from the spoken text.
- keyboard_control.py only ever sends a fixed set of key combinations
  (Enter/Escape/Space/Tab, Ctrl+C/V/A/Z) - there is no "type this text"
  capability anywhere in the codebase.
- intent_parser's OPEN_APPLICATION/PRESS_KEY targets only ever come from
  fixed allow-lists (see test_intent_parser.py for the exhaustive
  version of this).
- Wake-word matching is whole-word only - substrings don't activate.
- Greeting matching is whole-word only - "this" doesn't contain "hi" as
  a greeting.
- lock/shutdown/restart commands are unchanged.

No real destructive action is ever performed by these tests - all of
subprocess.Popen, os.system, webbrowser.open, and the ctypes/user32
calls are mocked throughout.
"""

from unittest.mock import patch

import commands
import jarvis as jarvis_module
import window_control


class FakeVoice:
    def __init__(self):
        self.spoken = []

    def speak(self, text):
        self.spoken.append(text)


def make_processor():
    voice = FakeVoice()
    return commands.CommandProcessor(voice), voice


# ---------------------------------------------------------------------
# Arbitrary shell / PowerShell command text is never executed
# ---------------------------------------------------------------------

def test_arbitrary_shell_looking_command_is_unknown_not_executed():
    processor, voice = make_processor()

    with patch("system_control.subprocess.Popen") as mock_popen, \
         patch("system_control.os.system") as mock_system:
        result = processor.process(
            "delete everything in c colon windows system32"
        )

    assert result is True
    mock_popen.assert_not_called()
    mock_system.assert_not_called()
    assert "don't know how to do that" in voice.spoken[-1]


def test_arbitrary_powershell_payload_text_is_unknown_not_executed():
    processor, voice = make_processor()

    with patch("system_control.subprocess.Popen") as mock_popen, \
         patch("system_control.os.system") as mock_system:
        result = processor.process(
            "invoke web request evil dot example dot com outfile payload exe"
        )

    assert result is True
    mock_popen.assert_not_called()
    mock_system.assert_not_called()
    assert "don't know how to do that" in voice.spoken[-1]


def test_opening_powershell_never_passes_spoken_text_as_an_argument():
    """Even when a dangerous-sounding phrase happens to contain the
    trigger word 'powershell', the actual subprocess call must still
    only ever be the fixed, argument-less ["powershell.exe"] - the rest
    of the spoken sentence must never reach Popen."""

    processor, voice = make_processor()

    dangerous_phrase = (
        "open powershell and then run del slash f slash s slash q "
        "c colon backslash windows"
    )

    with patch("system_control.subprocess.Popen") as mock_popen:
        result = processor.process(dangerous_phrase)

    assert result is True
    mock_popen.assert_called_once_with(["powershell.exe"], shell=False)


def test_opening_cmd_never_passes_spoken_text_as_an_argument():
    processor, voice = make_processor()

    with patch("system_control.subprocess.Popen") as mock_popen:
        result = processor.process(
            "open command prompt and format the c drive"
        )

    assert result is True
    mock_popen.assert_called_once_with(["cmd.exe"], shell=False)


# ---------------------------------------------------------------------
# Arbitrary keyboard text injection is never possible
# ---------------------------------------------------------------------

def test_type_arbitrary_text_command_is_unknown():
    """There is no 'type this text' capability anywhere in the codebase
    - keyboard_control.py only recognizes a fixed set of shortcuts."""

    processor, voice = make_processor()

    with patch("keyboard_control.input_control.press_key") as mock_press, \
         patch(
             "keyboard_control.input_control.press_key_combo"
         ) as mock_combo:
        result = processor.process(
            "type the following text rm dash rf slash"
        )

    assert result is True
    mock_press.assert_not_called()
    mock_combo.assert_not_called()
    assert "don't know how to do that" in voice.spoken[-1]


def test_press_unknown_key_is_not_sent_to_keyboard():
    processor, voice = make_processor()

    with patch("keyboard_control.input_control.press_key") as mock_press:
        result = processor.process("press the delete key")

    assert result is True
    mock_press.assert_not_called()


def test_keyboard_control_module_has_no_arbitrary_type_function():
    """Structural guarantee: keyboard_control.py exposes no function
    capable of sending arbitrary text as keystrokes."""

    import keyboard_control

    dangerous_names = ["type", "type_text", "send_text", "send_keys"]

    for name in dangerous_names:
        assert not hasattr(keyboard_control, name)


# ---------------------------------------------------------------------
# Unknown applications / unknown intents are rejected
# ---------------------------------------------------------------------

def test_unknown_application_is_rejected():
    processor, voice = make_processor()

    with patch("system_control.subprocess.Popen") as mock_popen, \
         patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("open some totally unknown application")

    assert result is True
    mock_popen.assert_not_called()
    mock_open.assert_not_called()
    assert "don't know how to do that" in voice.spoken[-1]


def test_unknown_intent_is_rejected():
    processor, voice = make_processor()

    result = processor.process("the weather looks nice today")

    assert result is True
    assert "don't know how to do that" in voice.spoken[-1]


# ---------------------------------------------------------------------
# Wake-word substring safety
# ---------------------------------------------------------------------

def test_wake_word_substring_does_not_activate():
    assert jarvis_module.extract_command_after_wake_word(
        "jarvison opened a new business today"
    ) is None
    assert jarvis_module.contains_wake_word(
        "jarvison opened a new business today"
    ) is False


def test_word_ending_in_wake_word_does_not_activate():
    assert jarvis_module.extract_command_after_wake_word(
        "myjarvis open chrome"
    ) is None


# ---------------------------------------------------------------------
# Greeting word-boundary safety ("this" must not match "hi")
# ---------------------------------------------------------------------

def test_this_does_not_trigger_hi_greeting():
    processor, voice = make_processor()

    result = processor.process("this is not a greeting")

    assert result is True
    assert "don't know how to do that" in voice.spoken[-1]


def test_this_window_commands_are_not_misrouted_to_greeting():
    processor, voice = make_processor()

    with patch(
        "window_control.user32.GetForegroundWindow", return_value=1
    ), patch("window_control.user32.ShowWindow") as mock_show:
        processor.process("minimize this window")

    assert "JARVIS. How can I help you?" not in voice.spoken
    mock_show.assert_called_once()


# ---------------------------------------------------------------------
# lock/shutdown/restart remain unchanged
# ---------------------------------------------------------------------

def test_lock_computer_unchanged():
    processor, voice = make_processor()

    with patch("system_control.os.system") as mock_system:
        result = processor.process("lock computer")

    assert result is True
    mock_system.assert_called_once_with(
        "rundll32.exe user32.dll,LockWorkStation"
    )


def test_shutdown_computer_unchanged():
    processor, voice = make_processor()

    with patch("system_control.os.system") as mock_system:
        result = processor.process("shutdown computer")

    assert result is True
    mock_system.assert_called_once_with("shutdown /s /t 5")


def test_restart_computer_unchanged():
    processor, voice = make_processor()

    with patch("system_control.os.system") as mock_system:
        result = processor.process("restart computer")

    assert result is True
    mock_system.assert_called_once_with("shutdown /r /t 5")


def test_lock_shutdown_restart_are_never_triggered_by_natural_phrasing_alone():
    """Natural-language politeness wrappers must not make these easier
    to trigger accidentally - only the exact existing phrases work,
    unchanged from before Phase 5."""

    processor, voice = make_processor()

    with patch("system_control.os.system") as mock_system:
        result = processor.process("can you shut everything down please")

    assert result is True
    mock_system.assert_not_called()
    assert "don't know how to do that" in voice.spoken[-1]


# ---------------------------------------------------------------------
# PHASE 6: targeted window control - allow-list-only target resolution
# ---------------------------------------------------------------------

def test_known_application_window_target_is_allowed():
    """'close chrome' names a known application - it must be allowed to
    act on a matching window (real API calls mocked)."""

    processor, voice = make_processor()

    with patch(
        "window_control.resolve_window_target", return_value=(True, 7)
    ), patch("window_control.user32.PostMessageW") as mock_post:
        result = processor.process("close chrome")

    assert result is True
    mock_post.assert_called_once_with(7, window_control.WM_CLOSE, 0, 0)


def test_unknown_application_window_target_is_rejected_no_enumeration():
    """'close spotify' names an application NOT in the fixed allow-list -
    window enumeration must never even be attempted, and no window
    action of any kind may occur."""

    processor, voice = make_processor()

    with patch("window_control._list_visible_window_titles") as mock_list, \
         patch("window_control.user32.PostMessageW") as mock_post, \
         patch("window_control.user32.ShowWindow") as mock_show:
        result = processor.process("close spotify")

    assert result is True
    mock_list.assert_not_called()
    mock_post.assert_not_called()
    mock_show.assert_not_called()
    assert "don't know how to do that" in voice.spoken[-1]


def test_arbitrary_spoken_window_title_is_rejected():
    """A phrase inventing a made-up window title (not a known
    application name) is NOT routed through by-name target resolution -
    window enumeration must never be attempted for it. It still contains
    the generic 'close'/'window' words, though, so it's legitimately
    handled by the existing untargeted close-the-focused-window command
    (unchanged, documented behavior) - never a fabricated-title search."""

    processor, voice = make_processor()

    with patch("window_control._list_visible_window_titles") as mock_list, \
         patch(
             "window_control.user32.GetForegroundWindow", return_value=1
         ), patch("window_control.user32.PostMessageW") as mock_post:
        result = processor.process(
            "close the window titled top secret passwords"
        )

    assert result is True
    mock_list.assert_not_called()
    mock_post.assert_called_once_with(1, window_control.WM_CLOSE, 0, 0)


def test_dangerous_looking_target_text_is_rejected():
    """A dangerous-sounding phrase with no known application name must
    be rejected outright - no window enumeration, no action."""

    processor, voice = make_processor()

    with patch("window_control._list_visible_window_titles") as mock_list:
        result = processor.process(
            "close the malware.exe process running in the background"
        )

    assert result is True
    mock_list.assert_not_called()
    assert "don't know how to do that" in voice.spoken[-1]


def test_dangerous_suffix_after_a_known_target_is_discarded():
    """Even when a dangerous-sounding phrase happens to also contain a
    known application name, only the fixed, safe by-name action is ever
    taken - the dangerous suffix is discarded, never used for anything."""

    processor, voice = make_processor()

    with patch(
        "window_control.resolve_window_target", return_value=(True, 7)
    ), patch("window_control.user32.PostMessageW") as mock_post:
        result = processor.process(
            "close chrome and then format the c drive"
        )

    assert result is True
    mock_post.assert_called_once_with(7, window_control.WM_CLOSE, 0, 0)


def test_no_target_window_commands_still_use_foreground_window():
    """Regression proof: commands with no named application must
    continue to act on GetForegroundWindow() exactly as before Phase 6 -
    the new by-name path must never be taken for these."""

    processor, voice = make_processor()

    with patch(
        "window_control.user32.GetForegroundWindow", return_value=99
    ), patch("window_control.user32.ShowWindow") as mock_show, \
         patch("window_control._list_visible_window_titles") as mock_list:
        result = processor.process("minimize this window")

    assert result is True
    mock_show.assert_called_once_with(99, window_control.SW_MINIMIZE)
    mock_list.assert_not_called()


def test_target_not_found_never_falls_back_to_foreground_window():
    """A known application that isn't currently open must report
    'not found' and must NEVER fall back to acting on whatever window
    currently has focus."""

    processor, voice = make_processor()

    with patch(
        "window_control.resolve_window_target", return_value=(True, None)
    ), patch(
        "window_control.user32.GetForegroundWindow"
    ) as mock_foreground, \
         patch("window_control.user32.ShowWindow") as mock_show:
        result = processor.process("minimize chrome")

    assert result is True
    mock_foreground.assert_not_called()
    mock_show.assert_not_called()
    assert "couldn't find an open Chrome window" in voice.spoken[-1]


def test_targeted_window_control_introduces_no_shell_execution():
    """Structural guarantee: acting on a named window never touches
    subprocess.Popen or os.system."""

    processor, voice = make_processor()

    with patch(
        "window_control.resolve_window_target", return_value=(True, 7)
    ), patch("window_control.user32.PostMessageW"), \
         patch("system_control.subprocess.Popen") as mock_popen, \
         patch("system_control.os.system") as mock_system:
        processor.process("close chrome")

    mock_popen.assert_not_called()
    mock_system.assert_not_called()


def test_targeted_window_control_introduces_no_keyboard_text_injection():
    """Structural guarantee: acting on a named window never touches the
    keyboard-injection primitives."""

    processor, voice = make_processor()

    with patch(
        "window_control.resolve_window_target", return_value=(True, 7)
    ), patch("window_control.user32.PostMessageW"), \
         patch("keyboard_control.input_control.press_key") as mock_press, \
         patch(
             "keyboard_control.input_control.press_key_combo"
         ) as mock_combo:
        processor.process("close chrome")

    mock_press.assert_not_called()
    mock_combo.assert_not_called()


# ---------------------------------------------------------------------
# PHASE 7: absolute volume / true mute-unmute - Core Audio security
# guarantees. volume_control.audio_endpoint.set_volume_percent is
# mocked at its actual point of use throughout - no real Core Audio
# COM call is ever made by these tests.
# ---------------------------------------------------------------------

def test_arbitrary_malformed_volume_text_never_becomes_a_core_audio_argument():
    """A grab-bag of dangerous-looking / malformed spoken volume
    phrases must never reach the Core Audio setter - each is either
    not a valid number at all, or outside the valid 0-100 domain."""

    processor, voice = make_processor()

    dangerous_phrases = [
        "set volume to 999999999999999999 percent",
        "set volume to -10 percent",
        "set volume to 40.5 percent",
        "set volume to forty percent",
        "set volume to 150 percent",
        "set volume to zero percent; rm -rf /",
    ]

    for phrase in dangerous_phrases:
        with patch(
            "volume_control.audio_endpoint.set_volume_percent"
        ) as mock_set:
            result = processor.process(phrase)

        assert result is True, phrase
        mock_set.assert_not_called()


def test_huge_numeric_volume_value_never_reaches_core_audio_setter():
    processor, voice = make_processor()

    with patch("volume_control.audio_endpoint.set_volume_percent") as mock_set:
        processor.process("set volume to 999999999999999999 percent")

    mock_set.assert_not_called()


def test_negative_volume_value_never_reaches_core_audio_setter():
    processor, voice = make_processor()

    with patch("volume_control.audio_endpoint.set_volume_percent") as mock_set:
        processor.process("set volume to -10 percent")

    mock_set.assert_not_called()


def test_decimal_spelled_out_and_malformed_values_never_reach_core_audio_setter():
    processor, voice = make_processor()

    for phrase in [
        "set volume to 40.5 percent",
        "set volume to forty percent",
        "set volume to abc percent",
    ]:
        with patch(
            "volume_control.audio_endpoint.set_volume_percent"
        ) as mock_set:
            processor.process(phrase)

        assert mock_set.call_count == 0, phrase


def test_volume_commands_introduce_no_shell_execution():
    """Structural guarantee, mirroring the Phase 6 window-control
    equivalent above: neither a valid nor a rejected volume command may
    ever touch subprocess.Popen or os.system."""

    processor, voice = make_processor()

    with patch("volume_control.audio_endpoint.set_volume_percent"), \
         patch("volume_control.audio_endpoint.set_mute"), \
         patch("system_control.subprocess.Popen") as mock_popen, \
         patch("system_control.os.system") as mock_system:
        processor.process("set volume to 40 percent")
        processor.process("mute")
        processor.process("unmute")
        processor.process("set volume to 999999999999999999 percent")

    mock_popen.assert_not_called()
    mock_system.assert_not_called()


def test_volume_commands_introduce_no_keyboard_text_injection():
    """Structural guarantee, mirroring the Phase 6 window-control
    equivalent above: mute/unmute/set-volume must never touch the
    keyboard-injection primitives (only 'volume up'/'volume down'
    legitimately use input_control.press_key, unchanged since Phase 3
    - not exercised by this test)."""

    processor, voice = make_processor()

    with patch("volume_control.audio_endpoint.set_volume_percent"), \
         patch("volume_control.audio_endpoint.set_mute"), \
         patch("keyboard_control.input_control.press_key") as mock_press, \
         patch(
             "keyboard_control.input_control.press_key_combo"
         ) as mock_combo:
        processor.process("set volume to 40 percent")
        processor.process("mute")
        processor.process("unmute")

    mock_press.assert_not_called()
    mock_combo.assert_not_called()
