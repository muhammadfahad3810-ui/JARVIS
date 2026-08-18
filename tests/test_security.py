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


# ---------------------------------------------------------------------
# PHASE 8: natural-language layer (command_parser extensions +
# natural_language.py multi-clause splitting) - security guarantees.
# No real Core Audio/Windows API/subprocess call is ever made by these
# tests - every real action primitive is mocked at its point of use.
# ---------------------------------------------------------------------

def test_natural_language_layer_introduces_no_shell_execution():
    """Neither the new command_parser synonym rules nor
    natural_language.split_into_clauses() may ever cause a shell
    command to run - proven across a mix of valid and rejected Phase 8
    phrasing, chained and unchained. Deliberately excludes phrases whose
    correct, safe action legitimately calls subprocess.Popen with fixed
    arguments (e.g. "open notepad and mute" -> Popen(["notepad.exe"]),
    already proven safe/fixed-argument in test_commands.py and
    test_security.py's pre-existing Popen-argument tests) - that is
    intended behavior, not a violation of this guarantee."""

    processor, voice = make_processor()

    phrases = [
        "make the volume 40 percent",
        "stop the music",
        "search google for python",
        "do something and open chrome",
        "make the volume 999999999999999999 percent",
    ]

    with patch("system_control.subprocess.Popen") as mock_popen, \
         patch("system_control.os.system") as mock_system, \
         patch("web_control.webbrowser.open"), \
         patch("web_control.os.path.exists", return_value=False), \
         patch("volume_control.audio_endpoint.set_mute"), \
         patch("volume_control.audio_endpoint.set_volume_percent"), \
         patch("media_control.input_control.press_key"):
        for phrase in phrases:
            processor.process(phrase)

    mock_popen.assert_not_called()
    mock_system.assert_not_called()


def test_natural_language_layer_introduces_no_keyboard_text_injection():
    """The Phase 8 layer must never touch the keyboard-injection
    primitives for phrases that have no keyboard/media action at all.
    Deliberately excludes "stop the music" - it correctly, legitimately
    presses VK_MEDIA_PLAY_PAUSE via the pre-existing media_control.py
    path (unchanged since Phase 3), which is not "text injection" (no
    arbitrary keystrokes, no spoken text becomes a key) - that is
    intended behavior, not a violation of this guarantee."""

    processor, voice = make_processor()

    phrases = [
        "make the volume 40 percent",
        "please mute",
        "search google for python",
    ]

    with patch(
        "keyboard_control.input_control.press_key"
    ) as mock_press, patch(
        "keyboard_control.input_control.press_key_combo"
    ) as mock_combo, patch(
        "volume_control.audio_endpoint.set_mute"
    ), patch(
        "volume_control.audio_endpoint.set_volume_percent"
    ), patch(
        "web_control.webbrowser.open"
    ):
        for phrase in phrases:
            processor.process(phrase)

    mock_press.assert_not_called()
    mock_combo.assert_not_called()


def test_natural_language_layer_introduces_no_direct_core_audio_calls():
    """command_parser.py and natural_language.py must never import or
    call audio_endpoint/comtypes directly - all volume/mute action
    still flows exclusively through volume_control.py, unchanged."""

    import inspect

    import command_parser
    import natural_language

    for module in (command_parser, natural_language):
        source = inspect.getsource(module)
        assert "audio_endpoint" not in source, module.__name__
        assert "comtypes" not in source, module.__name__


def test_natural_language_layer_introduces_no_direct_windows_api_calls():
    """command_parser.py and natural_language.py must never import
    ctypes or user32 directly - all real Windows API access still
    flows exclusively through the existing *_control.py modules."""

    import inspect

    import command_parser
    import natural_language

    for module in (command_parser, natural_language):
        source = inspect.getsource(module)
        assert "ctypes" not in source, module.__name__
        assert "user32" not in source, module.__name__


def test_natural_language_layer_cannot_bypass_command_processor():
    """natural_language.split_into_clauses() only ever returns strings
    for CommandProcessor.process() to interpret - it holds no reference
    to voice, commands, or any action module, so it structurally cannot
    call a handler directly, only decide how the text is grouped."""

    import inspect

    import natural_language

    source = inspect.getsource(natural_language)

    for forbidden in (
        "import commands",
        "import web_control",
        "import system_control",
        "import window_control",
        "import volume_control",
        "import media_control",
        "import screen_control",
        "import keyboard_control",
    ):
        assert forbidden not in source, forbidden


def test_huge_and_negative_volume_values_never_reach_core_audio_via_new_verbs():
    """Extends the Phase 7 rejection guarantee to the new Phase 8 verb
    forms ('make'/'turn'/'change' the volume) - out-of-range/malformed
    values must never reach the Core Audio setter regardless of which
    accepted verb phrasing was used to ask for them."""

    processor, voice = make_processor()

    dangerous_phrases = [
        "make the volume 999999999999999999 percent",
        "turn the volume to -10 percent",
        "change the volume to 40.5 percent",
        "make the volume forty percent",
        "make the volume 150 percent",
    ]

    for phrase in dangerous_phrases:
        with patch(
            "volume_control.audio_endpoint.set_volume_percent"
        ) as mock_set:
            result = processor.process(phrase)

        assert result is True, phrase
        mock_set.assert_not_called()


def test_chained_command_cannot_smuggle_an_unknown_dangerous_clause():
    """A chain containing one valid clause and one clause with no known
    command mapping must never partially execute the unknown clause -
    the all-or-nothing split safety (natural_language.py) guarantees
    this at the splitting layer, and this test proves it holds true
    end-to-end through the real CommandProcessor with every real action
    primitive mocked."""

    processor, voice = make_processor()

    with patch("system_control.subprocess.Popen") as mock_popen, \
         patch("system_control.os.system") as mock_system, \
         patch("volume_control.audio_endpoint.set_mute") as mock_mute, \
         patch("keyboard_control.input_control.press_key") as mock_press:
        processor.process("mute and delete everything")

    mock_popen.assert_not_called()
    mock_system.assert_not_called()
    mock_press.assert_not_called()
    # Whether "mute" alone still resolves once the split is discarded
    # depends only on the pre-existing, already-verified single-command
    # dispatch chain (see test_commands.py) - the security property
    # this test exists to prove is narrower and absolute: the unknown
    # "delete everything" clause is never independently dispatched.
    assert mock_mute.call_count <= 1


# ---------------------------------------------------------------------
# PHASE 9: dangerous-command confirmation layer - security guarantees.
# No real subprocess/os.system/browser/Core Audio/keyboard/window call
# is ever made by these tests - every real action primitive is mocked
# at its point of use.
# ---------------------------------------------------------------------

def test_phase_9_introduces_no_new_execution_primitive():
    """Structural guarantee: the confirmation layer added to
    commands.py must not introduce subprocess, os.system, ctypes,
    user32, comtypes, eval(, or exec( - it only gates the pre-existing,
    already-fixed system_control.handle_system() call."""

    import inspect

    import commands

    source = inspect.getsource(commands)

    for forbidden in (
        "import subprocess",
        "import ctypes",
        "comtypes",
        "eval(",
        "exec(",
    ):
        assert forbidden not in source, forbidden

    # os.system is never called directly by commands.py either - it
    # only ever reaches system_control.handle_system(), which already
    # owns the one hardcoded os.system() call site (unchanged).
    assert "os.system(" not in source


def test_confirmation_default_is_false():
    """The confirmation layer must be opt-in, not silently enabled -
    default False preserves all pre-Phase-9 lock/shutdown/restart
    behavior exactly."""

    import config

    assert config.REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS is False


def test_dangerous_command_with_mixed_action_blocks_all_real_primitives():
    """Security-framed version of the defect this phase's incident
    exposed: a dangerous phrase combined with ANY other recognized
    action must never let that other action reach a real primitive
    before confirmation - proven with every real-action surface mocked
    simultaneously, not just the one the phrase obviously targets."""

    import config
    import commands

    class FakeVoice:
        def __init__(self):
            self.spoken = []

        def speak(self, text):
            self.spoken.append(text)

    dangerous_phrases = [
        "lock computer and open chrome",
        "shutdown computer and search google",
        "restart computer and mute",
        "shutdown computer then search google",
    ]

    for phrase in dangerous_phrases:
        voice = FakeVoice()
        processor = commands.CommandProcessor(voice)

        with patch.object(
            config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
        ), patch("system_control.subprocess.Popen") as mock_popen, \
             patch("system_control.os.system") as mock_os_system, \
             patch("web_control.webbrowser.open") as mock_web_open, \
             patch("web_control.subprocess.Popen") as mock_web_popen, \
             patch("web_control.os.path.exists", return_value=False), \
             patch(
                 "volume_control.audio_endpoint.set_volume_percent"
             ) as mock_set_volume, \
             patch(
                 "volume_control.audio_endpoint.set_mute"
             ) as mock_set_mute, \
             patch(
                 "media_control.input_control.press_key"
             ) as mock_media_press, \
             patch(
                 "keyboard_control.input_control.press_key"
             ) as mock_kb_press, \
             patch(
                 "keyboard_control.input_control.press_key_combo"
             ) as mock_kb_combo, \
             patch("window_control.user32.ShowWindow") as mock_win_show, \
             patch(
                 "window_control.user32.PostMessageW"
             ) as mock_win_post:
            result = processor.process(phrase)

        assert result is True, phrase
        mock_popen.assert_not_called()
        mock_os_system.assert_not_called()
        mock_web_open.assert_not_called()
        mock_web_popen.assert_not_called()
        mock_set_volume.assert_not_called()
        mock_set_mute.assert_not_called()
        mock_media_press.assert_not_called()
        mock_kb_press.assert_not_called()
        mock_kb_combo.assert_not_called()
        mock_win_show.assert_not_called()
        mock_win_post.assert_not_called()


def test_confirmation_gate_only_accepts_the_fixed_allow_list():
    """Casual affirmatives NOT in CONFIRM_WORDS ("yeah", "sure", "ok",
    "yep") must NOT confirm a dangerous command - only the exact fixed
    allow-list (yes/confirm/confirmed) may. Prevents a misheard or
    loosely-matched reply from ever triggering a real system action."""

    import config
    import commands

    class FakeVoice:
        def __init__(self):
            self.spoken = []

        def speak(self, text):
            self.spoken.append(text)

    for casual_reply in ["yeah", "sure", "ok", "yep", "do it", "go ahead"]:
        voice = FakeVoice()
        processor = commands.CommandProcessor(voice)

        with patch.object(
            config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
        ), patch("system_control.os.system") as mock_system:
            processor.process("shutdown computer")
            result = processor.process(casual_reply)

        assert result is True, casual_reply
        mock_system.assert_not_called(), casual_reply
        assert voice.spoken[-1] == "Cancelled.", casual_reply


def test_confirmation_state_is_per_processor_instance_not_global():
    """Structural guarantee: pending confirmation is stored on the
    CommandProcessor instance (self._pending_confirmation), not at
    module level - a second, independent CommandProcessor must never
    see another instance's pending dangerous command."""

    import config
    import commands

    class FakeVoice:
        def __init__(self):
            self.spoken = []

        def speak(self, text):
            self.spoken.append(text)

    voice_a = FakeVoice()
    processor_a = commands.CommandProcessor(voice_a)
    voice_b = FakeVoice()
    processor_b = commands.CommandProcessor(voice_b)

    with patch.object(
        config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
    ), patch("system_control.os.system") as mock_system:
        processor_a.process("shutdown computer")

        result = processor_b.process("yes")

    mock_system.assert_not_called()
    assert "don't know how to do that" in voice_b.spoken[-1]


# ---------------------------------------------------------------------
# PHASE 10.3: conversational context / pending-slot-filling layer -
# security guarantees. No real subprocess/os.system/browser/Core
# Audio/keyboard/window call is ever made by these tests - every real
# action primitive is mocked at its point of use, exactly like every
# other section of this file.
# ---------------------------------------------------------------------

def test_context_manager_introduces_no_new_execution_primitive():
    """Structural guarantee: context_manager.py must not import or use
    subprocess, ctypes, comtypes, os.system, eval(, or exec() - it can
    only ever produce data (a PendingSlotRequest or a SlotResolution),
    never execute anything itself."""

    import inspect

    import context_manager

    source = inspect.getsource(context_manager)

    for forbidden in (
        "import subprocess",
        "import ctypes",
        "comtypes",
        "eval(",
        "exec(",
    ):
        assert forbidden not in source, forbidden

    assert "os.system(" not in source


def test_context_manager_imports_no_control_module():
    """Structural guarantee: context_manager.py must never import any
    of the control modules that can perform a real Windows/browser
    action, nor voice.py itself - it has no way to speak or act."""

    import ast
    import inspect

    import context_manager

    tree = ast.parse(inspect.getsource(context_manager))
    imported = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    forbidden_modules = {
        "web_control", "system_control", "window_control", "volume_control",
        "media_control", "keyboard_control", "screen_control", "voice",
        "subprocess", "ctypes",
    }

    assert imported & forbidden_modules == set()


def test_context_layer_default_is_false():
    """The context layer must be opt-in, not silently enabled - default
    False preserves all pre-Phase-10.3 behavior exactly."""

    import config

    assert config.ENABLE_CONTEXT_LAYER is False


def test_context_cannot_bypass_process_dangerous_command_stays_gated():
    """CRITICAL SAFETY TEST: with a search slot pending, a dangerous
    command must still be forced through the Phase 9 confirmation gate
    - proven with every real-action surface mocked simultaneously."""

    import config
    import commands
    import context_manager
    import intent_layer

    class FakeVoice:
        def __init__(self):
            self.spoken = []

        def speak(self, text):
            self.spoken.append(text)

    voice = FakeVoice()
    processor = commands.CommandProcessor(voice)
    processor._pending_slot = context_manager.PendingSlotRequest(
        intent=intent_layer.Intent.SEARCH,
        missing_slot="query",
        prompt="What should I search for?",
        created_turn=processor._context.turn_count,
    )

    with patch.object(config, "ENABLE_CONTEXT_LAYER", True), \
         patch.object(
             config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
         ), patch("system_control.subprocess.Popen") as mock_popen, \
         patch("system_control.os.system") as mock_os_system, \
         patch("web_control.webbrowser.open") as mock_web_open, \
         patch("web_control.subprocess.Popen") as mock_web_popen, \
         patch("web_control.os.path.exists", return_value=False), \
         patch(
             "volume_control.audio_endpoint.set_volume_percent"
         ) as mock_set_volume, \
         patch("volume_control.audio_endpoint.set_mute") as mock_set_mute, \
         patch(
             "media_control.input_control.press_key"
         ) as mock_media_press, \
         patch(
             "keyboard_control.input_control.press_key"
         ) as mock_kb_press, \
         patch(
             "keyboard_control.input_control.press_key_combo"
         ) as mock_kb_combo, \
         patch("window_control.user32.ShowWindow") as mock_win_show, \
         patch("window_control.user32.PostMessageW") as mock_win_post:
        result = processor.process("lock computer")

    assert result is True
    mock_popen.assert_not_called()
    mock_os_system.assert_not_called()
    mock_web_open.assert_not_called()
    mock_web_popen.assert_not_called()
    mock_set_volume.assert_not_called()
    mock_set_mute.assert_not_called()
    mock_media_press.assert_not_called()
    mock_kb_press.assert_not_called()
    mock_kb_combo.assert_not_called()
    mock_win_show.assert_not_called()
    mock_win_post.assert_not_called()
    assert "sure" in voice.spoken[-1].lower()
    assert processor._pending_confirmation == "lock computer"


def test_context_never_converts_dangerous_reply_into_a_search_query():
    """The pending slot's canonical rendering must never turn a
    dangerous phrase into "search for lock my computer" or similar -
    checked directly against the resolver, no mocking needed since it
    provably cannot execute anything."""

    import context_manager
    import intent_layer

    context = context_manager.ConversationContext()
    context.turn_count = 2

    pending = context_manager.PendingSlotRequest(
        intent=intent_layer.Intent.SEARCH,
        missing_slot="query",
        prompt="What should I search for?",
        created_turn=1,
    )

    for dangerous_reply in (
        "lock computer", "lock my computer",
        "shutdown computer", "shut down the computer",
        "restart computer", "restart the pc",
    ):
        resolution = context_manager.resolve_pending_slot(
            pending, dangerous_reply, context
        )

        assert resolution.kind != context_manager.ResolutionKind.RESOLVED, (
            dangerous_reply
        )
        assert resolution.canonical_command is None, dangerous_reply
        assert (
            resolution.canonical_command
            != f"search for {dangerous_reply}"
        )


def test_stale_pending_slot_never_silently_executes_an_old_command():
    """An expired pending slot must never be resolved as if it were
    still fresh - the next utterance is treated as a brand-new command
    instead, with the stale slot dropped."""

    import config
    import commands
    import context_manager
    import intent_layer

    class FakeVoice:
        def __init__(self):
            self.spoken = []

        def speak(self, text):
            self.spoken.append(text)

    voice = FakeVoice()
    processor = commands.CommandProcessor(voice)
    pending = context_manager.PendingSlotRequest(
        intent=intent_layer.Intent.SEARCH,
        missing_slot="query",
        prompt="What should I search for?",
        created_turn=processor._context.turn_count,
    )
    pending.created_at -= (config.CONTEXT_SLOT_TTL_SECONDS + 1)
    processor._pending_slot = pending

    with patch.object(config, "ENABLE_CONTEXT_LAYER", True), \
         patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("Spider-Man")

    assert result is True
    mock_open.assert_not_called()
    assert processor._pending_slot is None


def test_expired_pending_slot_is_cleared_not_left_dangling():
    """Whether resolved, dropped as a new command, or left unresolved,
    self._pending_slot must always end up None after being consumed -
    never left set for a future, unrelated turn to accidentally reuse."""

    import config
    import commands
    import context_manager
    import intent_layer

    class FakeVoice:
        def __init__(self):
            self.spoken = []

        def speak(self, text):
            self.spoken.append(text)

    for reply in ("Spider-Man", "", "open notepad", "lock computer"):
        voice = FakeVoice()
        processor = commands.CommandProcessor(voice)
        processor._pending_slot = context_manager.PendingSlotRequest(
            intent=intent_layer.Intent.SEARCH,
            missing_slot="query",
            prompt="What should I search for?",
            created_turn=processor._context.turn_count,
        )

        with patch.object(config, "ENABLE_CONTEXT_LAYER", True), \
             patch("web_control.webbrowser.open"), \
             patch("system_control.subprocess.Popen"), \
             patch("system_control.os.system"):
            processor.process(reply)

        assert processor._pending_slot is None, reply


def test_no_real_windows_action_occurs_across_phase_10_3_scenarios():
    """End-to-end sweep: every Phase 10.3 conversational scenario, with
    every real-action primitive mocked - none of them are ever called
    with anything other than the exact same fixed arguments this
    project has always used."""

    import config
    import commands
    import context_manager
    import intent_layer

    class FakeVoice:
        def __init__(self):
            self.spoken = []

        def speak(self, text):
            self.spoken.append(text)

    scenarios = [
        ("search youtube", None),
        ("Spider-Man", "search"),
        ("lock my computer", None),
        ("open chrome", None),
    ]

    for first_command, _label in scenarios:
        voice = FakeVoice()
        processor = commands.CommandProcessor(voice)

        if first_command == "Spider-Man":
            processor._pending_slot = context_manager.PendingSlotRequest(
                intent=intent_layer.Intent.SEARCH,
                missing_slot="query",
                prompt="What should I search for?",
                created_turn=processor._context.turn_count,
            )

        with patch.object(config, "ENABLE_CONTEXT_LAYER", True), \
             patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
             patch("system_control.subprocess.Popen") as mock_popen, \
             patch("system_control.os.system") as mock_os_system, \
             patch("web_control.webbrowser.open") as mock_web_open, \
             patch("web_control.subprocess.Popen") as mock_web_popen, \
             patch("web_control.os.path.exists", return_value=False):
            processor.process(first_command)

        if mock_os_system.called:
            mock_os_system.assert_called_once_with(
                "rundll32.exe user32.dll,LockWorkStation"
            )
        if mock_popen.called:
            mock_popen.assert_called_once_with(
                ["notepad.exe"], shell=False
            )


# ---------------------------------------------------------------------
# PHASE 10.4: contextual reference resolution - security guarantees.
# No real subprocess/os.system/browser/Core Audio/keyboard/window call
# is ever made by these tests - every real action primitive is mocked
# at its point of use, exactly like every other section of this file.
# ---------------------------------------------------------------------

def test_reference_resolution_introduces_no_new_execution_primitive():
    """Structural guarantee: context_manager.py must still contain no
    subprocess, ctypes, comtypes, os.system, eval(, or exec( after the
    Phase 10.4 additions - it can only ever produce data, never
    execute anything itself."""

    import inspect

    import context_manager

    source = inspect.getsource(context_manager)

    for forbidden in (
        "import subprocess",
        "import ctypes",
        "comtypes",
        "eval(",
        "exec(",
    ):
        assert forbidden not in source, forbidden

    assert "os.system(" not in source


def test_reference_resolution_imports_no_control_module():
    """Structural guarantee: context_manager.py still never imports any
    control module or voice.py - unchanged since Phase 10.3, verified
    again after the Phase 10.4 additions."""

    import ast
    import inspect

    import context_manager

    tree = ast.parse(inspect.getsource(context_manager))
    imported = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    forbidden_modules = {
        "web_control", "system_control", "window_control", "volume_control",
        "media_control", "keyboard_control", "screen_control", "voice",
        "subprocess", "ctypes",
    }

    assert imported & forbidden_modules == set()


def test_reference_resolution_default_is_false():
    """The reference-resolution layer must be opt-in, not silently
    enabled - default False preserves all pre-Phase-10.4 behavior
    exactly."""

    import config

    assert config.ENABLE_REFERENCE_RESOLUTION is False


def test_resolved_reference_can_never_be_a_dangerous_command():
    """CRITICAL SAFETY TEST: resolve_reference() can only ever render
    "open <app>" or "<minimize|maximize|restore|close|switch> <app>"
    for an app in intent_parser.KNOWN_APPLICATIONS - it structurally
    cannot produce "lock computer"/"shutdown computer"/"restart
    computer" or any other dangerous phrase, checked directly against
    every known application and every recognized verb."""

    import context_manager
    import intent_parser

    context = context_manager.ConversationContext()
    context.turn_count = 1

    dangerous_phrases = {
        "lock computer", "shutdown computer", "restart computer",
    }

    for app in intent_parser.KNOWN_APPLICATIONS:
        context.record(intent_parser.Intent.OPEN_APPLICATION, {"application": app})
        context.turn_count = 2

        for verb in context_manager.REFERENCE_VERBS:
            for pronoun in context_manager.REFERENCE_PRONOUNS:
                resolved = context_manager.resolve_reference(
                    f"{verb} {pronoun}", context
                )
                assert resolved not in dangerous_phrases


def test_reference_resolution_cannot_bypass_process_dangerous_command_stays_gated():
    """CRITICAL SAFETY TEST: naming an application and then saying a
    real dangerous command must still be forced through the Phase 9
    confirmation gate - proven with every real-action surface mocked
    simultaneously."""

    import config
    import commands

    class FakeVoice:
        def __init__(self):
            self.spoken = []

        def speak(self, text):
            self.spoken.append(text)

    voice = FakeVoice()
    processor = commands.CommandProcessor(voice)

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open"):
        processor.process("open chrome")

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch.object(
             config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
         ), patch("system_control.subprocess.Popen") as mock_popen, \
         patch("system_control.os.system") as mock_os_system, \
         patch("web_control.webbrowser.open") as mock_web_open, \
         patch("web_control.subprocess.Popen") as mock_web_popen, \
         patch("web_control.os.path.exists", return_value=False), \
         patch(
             "volume_control.audio_endpoint.set_volume_percent"
         ) as mock_set_volume, \
         patch("volume_control.audio_endpoint.set_mute") as mock_set_mute, \
         patch(
             "media_control.input_control.press_key"
         ) as mock_media_press, \
         patch(
             "keyboard_control.input_control.press_key"
         ) as mock_kb_press, \
         patch(
             "keyboard_control.input_control.press_key_combo"
         ) as mock_kb_combo, \
         patch("window_control.user32.ShowWindow") as mock_win_show, \
         patch("window_control.user32.PostMessageW") as mock_win_post:
        result = processor.process("lock computer")

    assert result is True
    mock_popen.assert_not_called()
    mock_os_system.assert_not_called()
    mock_web_open.assert_not_called()
    mock_web_popen.assert_not_called()
    mock_set_volume.assert_not_called()
    mock_set_mute.assert_not_called()
    mock_media_press.assert_not_called()
    mock_kb_press.assert_not_called()
    mock_kb_combo.assert_not_called()
    mock_win_show.assert_not_called()
    mock_win_post.assert_not_called()
    assert "sure" in voice.spoken[-1].lower()
    assert processor._pending_confirmation == "lock computer"


def test_expired_reference_never_silently_triggers_a_window_action():
    """A stale last-named-application record must never be used to
    resolve a reference once expired - the utterance is instead
    treated as an unrecognized command, with no window/application
    primitive ever called."""

    import config
    import commands

    class FakeVoice:
        def __init__(self):
            self.spoken = []

        def speak(self, text):
            self.spoken.append(text)

    voice = FakeVoice()
    processor = commands.CommandProcessor(voice)

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open"):
        processor.process("open chrome")

    processor._context.last_recorded_at -= (config.REFERENCE_TTL_SECONDS + 1)

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch("window_control.user32.ShowWindow") as mock_show, \
         patch("window_control.user32.PostMessageW") as mock_post, \
         patch("window_control.user32.SetForegroundWindow") as mock_setfg:
        result = processor.process("close it")

    assert result is True
    mock_show.assert_not_called()
    mock_post.assert_not_called()
    mock_setfg.assert_not_called()


def test_no_real_windows_action_occurs_across_phase_10_4_scenarios():
    """End-to-end sweep: every Phase 10.4 conversational scenario, with
    every real-action primitive mocked - none of them are ever called
    with anything other than the exact same fixed arguments this
    project has always used."""

    import config
    import commands

    class FakeVoice:
        def __init__(self):
            self.spoken = []

        def speak(self, text):
            self.spoken.append(text)

    for second_command in ("close it", "open it", "switch to that", "lock it", ""):
        voice = FakeVoice()
        processor = commands.CommandProcessor(voice)

        with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
             patch("web_control.os.path.exists", return_value=False), \
             patch("web_control.webbrowser.open"):
            processor.process("open chrome")

        # "open it" legitimately re-resolves to "open chrome" and is
        # expected to reach web_control.open_chrome() again (mocked
        # below, never a real action) - the real safety invariant
        # under test is that os.system (the dangerous-command
        # primitive) is NEVER reached for any of these five phrases.
        with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
             patch("system_control.subprocess.Popen"), \
             patch("system_control.os.system") as mock_os_system, \
             patch("web_control.subprocess.Popen"), \
             patch("web_control.os.path.exists", return_value=False), \
             patch(
                 "window_control.resolve_window_target",
                 return_value=(True, 1),
             ), patch("window_control.user32.ShowWindow"), \
             patch("window_control.user32.PostMessageW"), \
             patch("window_control.user32.SetForegroundWindow"), \
             patch("web_control.webbrowser.open"):
            processor.process(second_command)

        mock_os_system.assert_not_called()


# ---------------------------------------------------------------------
# PHASE 10.5: "again"/"once more" phrasing + repeat-search - security
# guarantees. No real subprocess/os.system/browser/Core Audio/
# keyboard/window call is ever made by these tests - every real action
# primitive is mocked at its point of use, exactly like every other
# section of this file.
# ---------------------------------------------------------------------

def test_phase_10_5_introduces_no_new_execution_primitive():
    """Structural guarantee: context_manager.py must still contain no
    subprocess, ctypes, comtypes, os.system, eval(, or exec( after the
    Phase 10.5 additions."""

    import inspect

    import context_manager

    source = inspect.getsource(context_manager)

    for forbidden in (
        "import subprocess",
        "import ctypes",
        "comtypes",
        "eval(",
        "exec(",
    ):
        assert forbidden not in source, forbidden

    assert "os.system(" not in source


def test_phase_10_5_imports_no_control_module():
    """Structural guarantee: context_manager.py still never imports any
    control module or voice.py after the Phase 10.5 additions."""

    import ast
    import inspect

    import context_manager

    tree = ast.parse(inspect.getsource(context_manager))
    imported = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    forbidden_modules = {
        "web_control", "system_control", "window_control", "volume_control",
        "media_control", "keyboard_control", "screen_control", "voice",
        "subprocess", "ctypes",
    }

    assert imported & forbidden_modules == set()


def test_phase_10_5_reuses_existing_flag_no_new_flag_added():
    """The scope explicitly forbids a second feature flag - Phase 10.5
    must reuse config.ENABLE_REFERENCE_RESOLUTION."""

    import config

    assert config.ENABLE_REFERENCE_RESOLUTION is False
    assert not hasattr(config, "ENABLE_SEARCH_REPEAT")
    assert not hasattr(config, "ENABLE_SEARCH_CONTEXT")
    assert not hasattr(config, "ENABLE_REPEAT_SEARCH")


def test_resolve_repeat_search_can_never_produce_a_bare_dangerous_command():
    """CRITICAL SAFETY TEST: resolve_repeat_search() can only ever
    render "search for <text>" - checked directly against every
    dangerous phrase used as the remembered query, proving it never
    renders a bare dangerous command regardless of what text was
    searched for previously."""

    import context_manager

    dangerous_phrases = (
        "lock computer", "shutdown computer", "restart computer",
    )

    for query in dangerous_phrases:
        context = context_manager.ConversationContext()
        context.record_search(query)

        resolved = context_manager.resolve_repeat_search(
            "search that again", context
        )

        assert resolved == f"search for {query}"
        assert resolved not in dangerous_phrases


def test_repeat_search_cannot_bypass_process_dangerous_command_stays_gated():
    """CRITICAL SAFETY TEST: performing a search and then giving a real
    dangerous command must still be forced through the Phase 9
    confirmation gate - proven with every real-action surface mocked
    simultaneously."""

    import config
    import commands

    class FakeVoice:
        def __init__(self):
            self.spoken = []

        def speak(self, text):
            self.spoken.append(text)

    voice = FakeVoice()
    processor = commands.CommandProcessor(voice)

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch("web_control.webbrowser.open"):
        processor.process("search for cats")

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch.object(
             config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
         ), patch("system_control.subprocess.Popen") as mock_popen, \
         patch("system_control.os.system") as mock_os_system, \
         patch("web_control.webbrowser.open") as mock_web_open, \
         patch("web_control.subprocess.Popen") as mock_web_popen, \
         patch("web_control.os.path.exists", return_value=False), \
         patch(
             "volume_control.audio_endpoint.set_volume_percent"
         ) as mock_set_volume, \
         patch("volume_control.audio_endpoint.set_mute") as mock_set_mute, \
         patch(
             "media_control.input_control.press_key"
         ) as mock_media_press, \
         patch(
             "keyboard_control.input_control.press_key"
         ) as mock_kb_press, \
         patch(
             "keyboard_control.input_control.press_key_combo"
         ) as mock_kb_combo, \
         patch("window_control.user32.ShowWindow") as mock_win_show, \
         patch("window_control.user32.PostMessageW") as mock_win_post:
        result = processor.process("lock computer")

    assert result is True
    mock_popen.assert_not_called()
    mock_os_system.assert_not_called()
    mock_web_open.assert_not_called()
    mock_web_popen.assert_not_called()
    mock_set_volume.assert_not_called()
    mock_set_mute.assert_not_called()
    mock_media_press.assert_not_called()
    mock_kb_press.assert_not_called()
    mock_kb_combo.assert_not_called()
    mock_win_show.assert_not_called()
    mock_win_post.assert_not_called()
    assert "sure" in voice.spoken[-1].lower()
    assert processor._pending_confirmation == "lock computer"


def test_expired_repeat_search_never_silently_triggers_a_browser_action():
    """A stale last-search-query record must never be used to resolve
    "search that again" once expired - the utterance falls through to
    the standard unrecognized-command response, with no browser
    primitive ever called."""

    import config
    import commands

    class FakeVoice:
        def __init__(self):
            self.spoken = []

        def speak(self, text):
            self.spoken.append(text)

    voice = FakeVoice()
    processor = commands.CommandProcessor(voice)

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch("web_control.webbrowser.open"):
        processor.process("search for cats")

    processor._context.last_search_recorded_at -= (
        config.SEARCH_REPEAT_TTL_SECONDS + 1
    )

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch("web_control.webbrowser.open") as mock_open:
        result = processor.process("search that again")

    assert result is True
    mock_open.assert_not_called()


def test_application_and_search_state_never_clobber_each_other():
    """Structural regression guarantee, checked directly against
    ConversationContext (no CommandProcessor needed): recording a
    search must never erase a previously-recorded application, and
    vice versa - the two are stored in genuinely separate fields."""

    import context_manager
    import intent_parser

    context = context_manager.ConversationContext()
    context.record(intent_parser.Intent.OPEN_APPLICATION, {"application": "chrome"})
    context.record_search("cats")
    context.record(intent_parser.Intent.OPEN_APPLICATION, {"application": "notepad"})

    assert context.last_search_query == "cats"
    assert context.last_entities == {"application": "notepad"}


def test_no_real_windows_or_browser_action_occurs_across_phase_10_5_scenarios():
    """End-to-end sweep: every Phase 10.5 conversational scenario, with
    every real-action primitive mocked - the dangerous-command
    primitive (os.system) is never reached for any of them."""

    import config
    import commands

    class FakeVoice:
        def __init__(self):
            self.spoken = []

        def speak(self, text):
            self.spoken.append(text)

    scenarios = [
        ("open youtube", "open it again"),
        ("open chrome", "open that once more"),
        ("search for cats", "search that again"),
        ("search for cats", "search again"),
        ("open chrome", ""),
    ]

    for first_command, second_command in scenarios:
        voice = FakeVoice()
        processor = commands.CommandProcessor(voice)

        with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
             patch("web_control.os.path.exists", return_value=False), \
             patch("web_control.webbrowser.open"):
            processor.process(first_command)

        with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
             patch("system_control.subprocess.Popen"), \
             patch("system_control.os.system") as mock_os_system, \
             patch("web_control.subprocess.Popen"), \
             patch("web_control.os.path.exists", return_value=False), \
             patch("web_control.webbrowser.open"):
            processor.process(second_command)

        mock_os_system.assert_not_called()


# =======================================================================
# PHASE 11.1: deterministic Urdu-script + Roman-Urdu normalization layer
# (see multilingual_normalizer.py). Unit-level coverage of the module
# itself lives in tests/test_multilingual_normalizer.py; end-to-end
# wiring coverage lives in tests/test_commands.py's own Phase 11.1
# section. This section holds the same class of structural/security
# guarantees every prior Phase 9-10.5 layer is held to here.
# =======================================================================

def test_multilingual_layer_flag_reflects_completed_rollout():
    """Rolled out (default True) after dedicated validation - see the
    Phase 11 validation report. Every command this layer can produce
    still only ever reaches a real control module by recursing back
    through CommandProcessor.process() (see commands.py's Phase 11.1
    insertion point), so the Phase 9 dangerous-command gate is
    unaffected by this flag's value either way."""

    import config

    assert config.ENABLE_MULTILINGUAL_LAYER is True


def test_multilingual_normalizer_imports_no_control_module():
    """Structural guarantee: multilingual_normalizer.py must never
    import any of the control modules that can perform a real Windows/
    browser action, nor voice.py, nor commands.py itself (which would
    also be a circular import) - it has no way to speak or act. Mirrors
    test_context_manager_imports_no_control_module() above exactly."""

    import ast
    import inspect

    import multilingual_normalizer

    tree = ast.parse(inspect.getsource(multilingual_normalizer))
    imported = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    forbidden_modules = {
        "web_control", "system_control", "window_control", "volume_control",
        "media_control", "keyboard_control", "screen_control", "voice",
        "commands", "subprocess", "ctypes", "comtypes", "os",
    }

    assert imported & forbidden_modules == set()
    assert imported == {"re", "intent_parser"}


def test_multilingual_normalizer_has_no_dangerous_command_intent_category():
    """Structural guarantee, not just a claim: intent_parser.Intent -
    the only vocabulary multilingual_normalizer.py's own outputs are
    validated against (see its module docstring) - has NO LOCK_COMPUTER/
    SHUTDOWN_COMPUTER/RESTART_COMPUTER member at all. This is what makes
    it structurally impossible for the Phase 11.1 layer to ever render
    one of those three phrases, for any input, in any language - not a
    behavioral choice this module could accidentally get wrong."""

    import intent_parser

    for forbidden in ("LOCK_COMPUTER", "SHUTDOWN_COMPUTER", "RESTART_COMPUTER"):
        assert not hasattr(intent_parser.Intent, forbidden)


def test_multilingual_layer_cannot_bypass_process_dangerous_command_stays_gated():
    """CRITICAL SAFETY TEST: with the multilingual layer enabled AND
    the Phase 9 confirmation gate enabled, an ordinary ENGLISH dangerous
    command must still be forced through confirmation exactly as
    before - proven with every real-action surface mocked
    simultaneously. This proves Phase 11.1 does not weaken the existing,
    unmodified, English-only Phase 9 gate in any way."""

    import commands
    import config

    class FakeVoice:
        def __init__(self):
            self.spoken = []

        def speak(self, text):
            self.spoken.append(text)

    voice = FakeVoice()
    processor = commands.CommandProcessor(voice)

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch.object(
             config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
         ), \
         patch("system_control.subprocess.Popen") as mock_popen, \
         patch("system_control.os.system") as mock_os_system:
        result = processor.process("shutdown computer")

    assert result is True
    mock_popen.assert_not_called()
    mock_os_system.assert_not_called()
    assert "sure" in voice.spoken[-1].lower()


def test_multilingual_dangerous_commands_never_execute_before_confirmation():
    """CRITICAL SAFETY TEST (Phase 11.2, section D): with REQUIRE_
    CONFIRMATION_FOR_DANGEROUS_COMMANDS=True and ENABLE_MULTILINGUAL_
    LAYER=True, every multilingual dangerous-command paraphrase - Urdu
    script, Roman Urdu, and mixed-language, for all three of lock/
    shutdown/restart - must reach the existing Phase 9 confirmation
    gate and must NOT execute before confirmation, with every real-
    action primitive mocked and proven uncalled."""

    import commands
    import config

    class FakeVoice:
        def __init__(self):
            self.spoken = []

        def speak(self, text):
            self.spoken.append(text)

    dangerous_paraphrases = (
        ("کمپیوٹر لاک کرو", "lock computer"),
        ("computer lock karo", "lock computer"),
        ("computer ko lock karo", "lock computer"),
        ("computer کو lock کرو", "lock computer"),
        ("کمپیوٹر بند کرو", "shutdown computer"),
        ("computer band karo", "shutdown computer"),
        ("کمپیوٹر shutdown کرو", "shutdown computer"),
        ("کمپیوٹر ری اسٹارٹ کرو", "restart computer"),
        ("computer restart karo", "restart computer"),
        ("کمپیوٹر ko restart karo", "restart computer"),
    )

    for phrase, expected_canonical in dangerous_paraphrases:

        voice = FakeVoice()
        processor = commands.CommandProcessor(voice)

        with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
             patch.object(
                 config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
             ), \
             patch("system_control.subprocess.Popen") as mock_popen, \
             patch("system_control.os.system") as mock_os_system, \
             patch("web_control.subprocess.Popen") as mock_web_popen, \
             patch("web_control.os.path.exists", return_value=False), \
             patch("web_control.webbrowser.open") as mock_web_open:
            result = processor.process(phrase)

        assert result is True, phrase
        mock_popen.assert_not_called()
        mock_os_system.assert_not_called()
        mock_web_popen.assert_not_called()
        mock_web_open.assert_not_called()
        assert "sure" in voice.spoken[-1].lower(), phrase
        assert processor._pending_confirmation == expected_canonical, phrase


def test_multilingual_dangerous_commands_reach_existing_mocked_execution_path_after_yes():
    """CRITICAL SAFETY TEST (Phase 11.2, sections D/F): after the "yes"
    confirmation, each multilingual dangerous-command paraphrase must
    reach the EXACT SAME existing, unmodified, hardcoded system_
    control.py call the equivalent English phrase already reaches - no
    new execution primitive, no spoken-text-derived argument."""

    import commands
    import config

    class FakeVoice:
        def __init__(self):
            self.spoken = []

        def speak(self, text):
            self.spoken.append(text)

    dangerous_paraphrases_and_calls = (
        ("کمپیوٹر لاک کرو", "rundll32.exe user32.dll,LockWorkStation"),
        ("computer band karo", "shutdown /s /t 5"),
        ("کمپیوٹر ko restart karo", "shutdown /r /t 5"),
    )

    for phrase, expected_os_system_call in dangerous_paraphrases_and_calls:

        voice = FakeVoice()
        processor = commands.CommandProcessor(voice)

        with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
             patch.object(
                 config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
             ), patch("system_control.os.system") as mock_os_system:
            processor.process(phrase)
            result = processor.process("yes")

        assert result is True, phrase
        mock_os_system.assert_called_once_with(expected_os_system_call)


def test_multilingual_dangerous_command_rejected_confirmation_never_executes():
    """CRITICAL SAFETY TEST (Phase 11.2, section E): a rejected ("no")
    confirmation for a multilingual dangerous command must never
    execute - mirrors the existing English rejection test exactly."""

    import commands
    import config

    class FakeVoice:
        def __init__(self):
            self.spoken = []

        def speak(self, text):
            self.spoken.append(text)

    voice = FakeVoice()
    processor = commands.CommandProcessor(voice)

    with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
         patch.object(
             config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
         ), \
         patch("system_control.subprocess.Popen") as mock_popen, \
         patch("system_control.os.system") as mock_os_system:
        processor.process("کمپیوٹر لاک کرو")
        result = processor.process("no")

    assert result is True
    mock_popen.assert_not_called()
    mock_os_system.assert_not_called()
    assert voice.spoken[-1] == "Cancelled."


def test_multilingual_layer_never_executes_a_dangerous_action_when_unrecognized():
    """A dangerous-SOUNDING but NOT actually matching phrase (missing
    the required "computer"/"کمپیوٹر" noun, or otherwise outside the
    explicit multi-word pattern) must still fall through to the
    standard unknown-command response, with every real-action primitive
    mocked and proven uncalled - proving Phase 11.2 did not turn
    dangerous-command recognition into a broad, over-triggering
    substring detector."""

    import commands
    import config

    class FakeVoice:
        def __init__(self):
            self.spoken = []

        def speak(self, text):
            self.spoken.append(text)

    not_actually_dangerous = (
        "lock karo",
        # Phase 11.7: bare "بند کرو" is no longer in this bucket - it is
        # now a deliberately recognized, SAFE exit phrase (see
        # multilingual_normalizer._AMBIGUOUS_EXIT_MARKERS and
        # test_multilingual_normalizer.py's own Phase 11.7 section) -
        # "shutdown karo" (still unrecognized bare, same as "lock karo"/
        # "restart karo" above) keeps this test's "bare action verb
        # without the computer noun" coverage for the shutdown action.
        "shutdown karo",
        "restart karo",
        "computer lock karobar",
    )

    for phrase in not_actually_dangerous:

        voice = FakeVoice()
        processor = commands.CommandProcessor(voice)

        with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
             patch("system_control.subprocess.Popen") as mock_popen, \
             patch("system_control.os.system") as mock_os_system, \
             patch("web_control.subprocess.Popen") as mock_web_popen, \
             patch("web_control.os.path.exists", return_value=False), \
             patch("web_control.webbrowser.open") as mock_web_open:
            result = processor.process(phrase)

        assert result is True, phrase
        mock_popen.assert_not_called()
        mock_os_system.assert_not_called()
        mock_web_popen.assert_not_called()
        mock_web_open.assert_not_called()
        assert voice.spoken == ["I heard you, but I don't know how to do that yet."], phrase


# =======================================================================
# PHASE 11.7: security regression coverage for the "finish the job"
# pass - safe targeted "close <app>" (new: multilingual_normalizer.
# _check_close_application() + intent_layer.TARGETED_ACTION_SYNONYMS_
# UR), the generalized bare "band karo"/"بند کرو" exit collision guard,
# and Urdu-script exit/dangerous-command interaction. Every test here
# proves a NEGATIVE (a dangerous action is never triggered), mirroring
# this file's own established style throughout.
# =======================================================================

def test_close_app_synonyms_never_execute_a_dangerous_system_call():
    """"youtube band karo"/"chrome band karo"-style phrases must never
    reach system_control.os.system()/subprocess.Popen() (the dangerous-
    command execution primitives) - proven with every real-action
    surface mocked, regardless of which layer (intent_layer.py's new
    TARGETED_ACTION_SYNONYMS_UR, or multilingual_normalizer.py's own
    _check_close_application()) actually resolves the phrase."""

    import config

    close_app_phrases = (
        "youtube band karo",
        "youtube band kar do",
        "youtube close karo",
        "youtube بند کرو",
        "github band karo",
        "chrome band karo",  # documented limitation: opens, doesn't close
    )

    for phrase in close_app_phrases:

        voice = FakeVoice()
        processor = commands.CommandProcessor(voice)

        with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
             patch("system_control.subprocess.Popen") as mock_popen, \
             patch("system_control.os.system") as mock_os_system, \
             patch("window_control.user32.PostMessageW"), \
             patch("window_control.user32.GetForegroundWindow", return_value=0), \
             patch(
                 "window_control.find_window_by_application", return_value=1
             ), \
             patch("web_control.os.path.exists", return_value=False), \
             patch("web_control.webbrowser.open"):
            result = processor.process(phrase)

        assert result is True, phrase
        assert result is not False, phrase
        mock_popen.assert_not_called()
        mock_os_system.assert_not_called()


def test_close_app_synonyms_never_exit_jarvis():
    """None of the "close <app>" phrasings may stop the run loop (exit
    returns False) - closing an application and exiting JARVIS must
    remain completely distinct outcomes."""

    import config

    close_app_phrases = (
        "youtube band karo", "youtube band kar do", "youtube close karo",
        "youtube بند کرو", "github band karo", "chrome band karo",
    )

    for phrase in close_app_phrases:

        voice = FakeVoice()
        processor = commands.CommandProcessor(voice)

        with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
             patch("window_control.user32.PostMessageW"), \
             patch("window_control.user32.GetForegroundWindow", return_value=0), \
             patch(
                 "window_control.find_window_by_application", return_value=1
             ), \
             patch("web_control.os.path.exists", return_value=False), \
             patch("web_control.webbrowser.open"):
            result = processor.process(phrase)

        assert result is not False, phrase


def test_bare_band_karo_family_never_executes_a_dangerous_system_call():
    """Bare "band karo"/"بند کرو"/"band ho jao"/"بند ہو جاؤ" (no
    "computer"/"کمپیوٹر" noun) map to the SAFE exit path only - never
    system_control.os.system()/subprocess.Popen()."""

    import config

    exit_phrases = (
        "band karo", "بند کرو", "band ho jao", "بند ہو جاؤ",
        "off ho jao", "آف ہو جاؤ",
    )

    for phrase in exit_phrases:

        voice = FakeVoice()
        processor = commands.CommandProcessor(voice)

        with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
             patch("system_control.subprocess.Popen") as mock_popen, \
             patch("system_control.os.system") as mock_os_system:
            result = processor.process(phrase)

        assert result is False, phrase  # the safe exit path
        mock_popen.assert_not_called()
        mock_os_system.assert_not_called()
        assert "Going offline" in voice.spoken[-1], phrase


def test_computer_noun_with_band_karo_family_still_requires_confirmation():
    """The generalized bare-exit-marker guard must never weaken the
    Phase 9 confirmation gate: "computer band karo"/"کمپیوٹر بند کرو"
    still prompt for confirmation and never call os.system() before an
    explicit "yes"."""

    import config

    dangerous_phrases = ("computer band karo", "کمپیوٹر بند کرو")

    for phrase in dangerous_phrases:

        voice = FakeVoice()
        processor = commands.CommandProcessor(voice)

        with patch.object(config, "ENABLE_MULTILINGUAL_LAYER", True), \
             patch.object(
                 config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
             ), patch("system_control.os.system") as mock_system:
            result = processor.process(phrase)

        assert result is True, phrase
        mock_system.assert_not_called()
        assert "sure" in voice.spoken[-1].lower(), phrase
        assert "shut down" in voice.spoken[-1].lower(), phrase


def test_intent_layer_urdu_close_synonym_never_produces_a_dangerous_intent():
    """Structural proof at the intent_layer.py level: no combination of
    a KNOWN_APPLICATIONS name with TARGETED_ACTION_SYNONYMS_UR can ever
    produce anything other than a TARGETED_WINDOW_ACTION frame with
    action="close" - never LOCK_COMPUTER/SHUTDOWN_COMPUTER/
    RESTART_COMPUTER."""

    import intent_layer
    import intent_parser

    dangerous_intents = {
        intent_layer.Intent.LOCK_COMPUTER,
        intent_layer.Intent.SHUTDOWN_COMPUTER,
        intent_layer.Intent.RESTART_COMPUTER,
    }

    for app in intent_parser.KNOWN_APPLICATIONS:
        for synonym in intent_layer.TARGETED_ACTION_SYNONYMS_UR:
            frames = intent_layer.understand(f"{app} {synonym}")
            for frame in frames:
                assert frame.intent not in dangerous_intents, (app, synonym)


def test_intent_layer_urdu_close_synonym_word_boundary_mid_word_safety():
    """"karobar" ("business") must never be mistaken for "karo" at the
    intent_layer.py level either - same false-positive class already
    guarded against in multilingual_normalizer.py, now also verified
    for intent_layer.py's own new synonym dict."""

    import intent_layer

    frames = intent_layer.understand("youtube band karobar")
    assert not any(
        f.intent == intent_layer.Intent.TARGETED_WINDOW_ACTION for f in frames
    )


# =======================================================================
# PHASE 11.9: security regression coverage for the wake-word-omission
# recovery path (jarvis.resolve_wake_word_omission() /
# Jarvis._maybe_recover_omitted_wake_word()). The central risk this
# phase introduces is a NEW way for text to reach CommandProcessor.
# process() without the wake word having been said - every test here
# proves that path can never reach a dangerous action, with or without
# the feature flag, with or without an explicit "yes" reply.
# =======================================================================

def test_resolve_wake_word_omission_full_dangerous_phrase_sweep_never_dangerous():
    """Every dangerous marker phrase this project knows about, in every
    language multilingual_normalizer.py supports, combined with the
    "computer"/"کمپیوٹر" noun exactly as _dangerous_pattern() requires -
    run through resolve_wake_word_omission() - must never produce a
    dangerous canonical command. Mirrors the exhaustive sweep style
    already used for multilingual_normalizer.py/intent_layer.py
    themselves, one level up at the jarvis.py integration point."""

    import jarvis as jarvis_module_local
    import multilingual_normalizer

    combos = []

    for noun in ("computer", "کمپیوٹر"):
        for action_phrases in (
            multilingual_normalizer.LOCK_ACTION_PHRASES,
            multilingual_normalizer.SHUTDOWN_ACTION_PHRASES,
            multilingual_normalizer.RESTART_ACTION_PHRASES,
        ):
            for action in action_phrases:
                combos.append(f"{noun} {action}")
                combos.append(f"{noun} ko {action}")

    # English/intent_layer-style dangerous phrasings.
    combos += [
        "shut down the computer",
        "shut off the computer",
        "power off the computer",
        "turn off the computer",
        "switch off the computer",
        "restart the computer",
        "reboot the computer",
        "restart the machine",
        "restart the pc",
        "lock the computer",
        "lock the workstation",
        "lock my computer",
    ]

    for phrase in combos:
        result = jarvis_module_local.resolve_wake_word_omission(phrase)
        assert result not in commands.DANGEROUS_COMMANDS, phrase
        assert result is None, phrase


def test_wake_word_omission_dangerous_phrase_never_calls_real_system_call():
    """End-to-end: with the tolerance flag ON, a dangerous phrase heard
    WITHOUT the wake word must never reach system_control.os.system()
    or subprocess.Popen() - not even after this path's own
    confirmation step, because it's never offered a prompt at all."""

    import config

    dangerous_phrases = (
        "shut down the computer",
        "computer band karo",
        "کمپیوٹر بند کرو",
        "lock the computer",
        "computer lock karo",
        "restart the computer",
        "computer restart karo",
    )

    for phrase in dangerous_phrases:

        voice = FakeVoice()

        with patch("jarvis.voice.Voice") as mock_voice_cls, \
             patch("jarvis.speech.Speech") as mock_speech_cls:

            mock_voice_cls.return_value = voice

            from unittest.mock import MagicMock
            fake_speech = MagicMock()
            fake_speech.listen.side_effect = [phrase]
            mock_speech_cls.return_value = fake_speech

            j = jarvis_module.Jarvis()

        with patch.object(config, "ENABLE_WAKE_WORD_OMISSION_TOLERANCE", True), \
             patch("system_control.os.system") as mock_system, \
             patch("system_control.subprocess.Popen") as mock_popen:
            j.wait_for_wake_word()

        mock_system.assert_not_called(), phrase
        mock_popen.assert_not_called(), phrase
        assert voice.spoken == [], phrase


def test_wake_word_present_dangerous_command_confirmation_unaffected_by_phase_11_9():
    """Re-verification: the EXISTING Phase 9 dangerous-command
    confirmation flow, reached the normal way (wake word present), is
    completely unaffected by this phase's changes."""

    import config

    processor, voice = make_processor()

    with patch.object(
        config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
    ), patch("system_control.os.system") as mock_system:
        result = processor.process("shutdown computer")

    assert result is True
    mock_system.assert_not_called()
    assert "sure" in voice.spoken[-1].lower()

    with patch("system_control.os.system") as mock_system:
        result = processor.process("yes")

    assert result is True
    mock_system.assert_called_once_with("shutdown /s /t 5")


def test_wake_word_omission_recovery_reuses_process_so_dangerous_gate_still_applies():
    """Structural proof: Jarvis._maybe_recover_omitted_wake_word() only
    ever executes a resolved command through self.process_command()
    (-> commands.CommandProcessor.process()) - the exact same entry
    point, and therefore the exact same unconditional Phase 9 gate at
    the top of process(), that every other command in this project
    already goes through. Verified here by confirming a resolved
    NON-dangerous command, once confirmed with "yes", still passes
    through a REAL (unmocked) CommandProcessor.process() call - not a
    parallel/bypassing execution path."""

    import config

    with patch("jarvis.voice.Voice") as mock_voice_cls, \
         patch("jarvis.speech.Speech") as mock_speech_cls:

        voice = FakeVoice()
        mock_voice_cls.return_value = voice

        from unittest.mock import MagicMock
        fake_speech = MagicMock()
        fake_speech.listen.side_effect = ["time kya hai"]
        fake_speech.listen_with_retry.return_value = "yes"
        mock_speech_cls.return_value = fake_speech

        j = jarvis_module.Jarvis()

    real_process = j.commands.process
    calls = []

    def spy_process(command):
        calls.append(command)
        return real_process(command)

    with patch.object(config, "ENABLE_WAKE_WORD_OMISSION_TOLERANCE", True), \
         patch.object(j.commands, "process", side_effect=spy_process):
        j.wait_for_wake_word()

    assert calls == ["what time is it"]


def test_wake_word_omission_never_raises_on_console_hostile_unicode_text():
    """Combines the Step 2 (console hardening) and Step 3 (wake-word
    omission) fixes: text that would have crashed the Phase 11.8
    session's console (see test_wake_word.py's PROBLEM_TEXT_SAMPLES)
    must not crash resolve_wake_word_omission() either, and must not
    resolve to any action - unrecognized noise/hallucination text stays
    silent."""

    import jarvis as jarvis_module_local

    weird_samples = (
        "पखि़नै हुचं यहें",
        "そんないので",
        "\U0001F389\U0001F389",
    )

    for sample in weird_samples:
        result = jarvis_module_local.resolve_wake_word_omission(sample)
        assert result not in commands.DANGEROUS_COMMANDS


# =======================================================================
# PHASE 11.11: security regression coverage for the STT/backend
# reliability changes - the wider wake-word-recovery confirmation word
# list (Step 7), and the Whisper confidence gate (Step 5/6). Every
# test proves a NEGATIVE: the dangerous-command gate is unaffected, and
# a low-confidence/hallucinated Whisper result can never become an
# executed command.
# =======================================================================

def test_dangerous_command_confirmation_gate_unaffected_by_wider_recovery_word_list():
    """Re-verification, after Step 7's changes: "yeah" (now valid for
    the wake-word-recovery flow) still does NOT confirm a dangerous
    command through the REAL, unmocked Phase 9 gate - the two
    confirmation word lists are genuinely separate, not just in a unit
    test but through the actual CommandProcessor.process() path."""

    import config

    for casual_reply in ["yeah", "haan", "han", "جی ہاں", "جی"]:

        voice = FakeVoice()
        processor = commands.CommandProcessor(voice)

        with patch.object(
            config, "REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS", True
        ), patch("system_control.os.system") as mock_system:
            processor.process("shutdown computer")
            result = processor.process(casual_reply)

        assert result is True, casual_reply
        mock_system.assert_not_called(), casual_reply
        assert voice.spoken[-1] == "Cancelled.", casual_reply


def test_commands_confirm_words_list_is_byte_for_byte_unchanged():
    """Structural proof, not just behavioral: commands.CONFIRM_WORDS
    itself was never touched by Phase 11.11 - the exact same three
    words as every prior phase."""

    assert commands.CONFIRM_WORDS == ["yes", "confirm", "confirmed"]


def test_wake_word_recovery_never_executes_a_dangerous_command_even_with_wider_confirm_words():
    """End-to-end, with BOTH new capabilities on at once: a dangerous
    phrase heard without the wake word must never be offered a "did
    you mean" prompt (resolve_wake_word_omission() structurally
    excludes dangerous commands - see its own docstring), regardless of
    how permissive the confirmation word list is."""

    import config

    dangerous_phrases = (
        "shut down the computer", "computer band karo", "کمپیوٹر بند کرو",
    )

    for phrase in dangerous_phrases:

        voice = FakeVoice()

        with patch("jarvis.voice.Voice") as mock_voice_cls, \
             patch("jarvis.speech.Speech") as mock_speech_cls:

            mock_voice_cls.return_value = voice

            from unittest.mock import MagicMock
            fake_speech = MagicMock()
            fake_speech.listen.side_effect = [phrase]
            fake_speech.listen_with_retry.return_value = "yeah"
            mock_speech_cls.return_value = fake_speech

            j = jarvis_module.Jarvis()

        with patch.object(config, "ENABLE_WAKE_WORD_OMISSION_TOLERANCE", True), \
             patch("system_control.os.system") as mock_system:
            j.wait_for_wake_word()

        mock_system.assert_not_called(), phrase
        assert voice.spoken == [], phrase


# ---- Whisper confidence gate: a hallucination can never become an
# executed command ----

def test_whisper_hallucination_never_executes_even_if_it_resembles_a_command():
    """The realistic worst case: Whisper hallucinates text that
    HAPPENS to resemble a real command (e.g. "mute") from pure noise.
    Even with the confidence gate OFF (today's default), this can only
    ever reach the SAME wake-word requirement (and, if enabled, the
    Step 7 explicit-confirmation prompt) every other unintentional
    utterance already goes through - it can never execute directly."""

    import config

    voice = FakeVoice()

    with patch("jarvis.voice.Voice") as mock_voice_cls, \
         patch("jarvis.speech.Speech") as mock_speech_cls:

        mock_voice_cls.return_value = voice

        from unittest.mock import MagicMock
        fake_speech = MagicMock()
        # No wake word anywhere in the hallucinated text.
        fake_speech.listen.side_effect = ["mute"]
        mock_speech_cls.return_value = fake_speech

        j = jarvis_module.Jarvis()

    with patch.object(config, "ENABLE_WAKE_WORD_OMISSION_TOLERANCE", False), \
         patch("volume_control.audio_endpoint.set_mute") as mock_mute:
        j.wait_for_wake_word()

    mock_mute.assert_not_called()
    assert voice.spoken == []


def test_whisper_confidence_gate_rejection_prevents_hallucination_from_reaching_wake_word_check():
    """Direct proof at the Speech level: with the gate ON, a low-
    confidence Whisper hallucination never even reaches listen()'s
    return value - so jarvis.py's wake-word check never sees it at
    all, regardless of what it says."""

    import config
    import speech as speech_module
    import speech_recognition as sr
    import stt_backend

    class FakeVoice:
        def speak(self, text):
            pass

    s = speech_module.Speech(FakeVoice())
    fake_audio = object()

    with patch.object(config, "ENABLE_WHISPER_CONFIDENCE_GATE", True), \
         patch("speech.sr.Microphone"), \
         patch.object(s.recognizer, "listen", return_value=fake_audio), \
         patch.object(
             s.recognizer, "recognize_google",
             side_effect=sr.UnknownValueError()
         ), \
         patch.object(s.offline_backend, "is_available", return_value=True), \
         patch.object(
             s.recognizer, "recognize_faster_whisper",
             return_value={
                 "text": "band ho jao",  # would-be exit phrase
                 "segments": [],
                 "language": "ur",
             },
         ):
        # Force a low-confidence signal via the real recognize() path
        # by patching the backend's own confidence computation result.
        with patch(
            "stt_backend._whisper_confidence_signal",
            return_value=(0.9, -4.0),
        ):
            result = s.listen()

    assert result == ""
    assert s.last_diagnostics["whisper_rejected_low_confidence"] is True
