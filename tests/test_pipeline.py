"""End-to-end pipeline tests: fake microphone text -> wake word
extraction -> command_parser.normalize() -> CommandProcessor -> mocked
Windows/browser action.

Everything that would touch the real world is mocked: voice.Voice,
speech.Speech (no real microphone/TTS engine), and the actual
webbrowser.open / subprocess.Popen / os.system / ctypes calls at the
point of use. No real microphone, TTS, or destructive Windows action
ever runs during these tests.
"""

from unittest.mock import MagicMock, patch

import config
import jarvis as jarvis_module
import window_control


class FakeVoice:
    def __init__(self):
        self.spoken = []

    def speak(self, text):
        self.spoken.append(text)


def make_jarvis(listen_side_effect=None, listen_with_retry_return=None):
    """Build a real Jarvis instance with voice.Voice and speech.Speech
    replaced by fakes, so no real microphone or TTS engine is touched."""

    with patch("jarvis.voice.Voice") as mock_voice_cls, \
         patch("jarvis.speech.Speech") as mock_speech_cls:

        fake_voice = FakeVoice()
        mock_voice_cls.return_value = fake_voice

        fake_speech = MagicMock()

        if listen_side_effect is not None:
            fake_speech.listen.side_effect = listen_side_effect

        if listen_with_retry_return is not None:
            fake_speech.listen_with_retry.return_value = listen_with_retry_return

        mock_speech_cls.return_value = fake_speech

        j = jarvis_module.Jarvis()

    return j, fake_voice, fake_speech


def test_pipeline_open_chrome_via_natural_language_verb():
    """'jarvis launch chrome' -> wake word stripped -> command_parser
    rewrites 'launch chrome' to 'open chrome' -> web_control opens it."""

    j, voice, fake_speech = make_jarvis(
        listen_side_effect=["jarvis launch chrome"]
    )

    with patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open") as mock_open:
        j.wait_for_wake_word()

    mock_open.assert_called_once_with("https://www.google.com")


def test_pipeline_repeated_wake_word_and_search_synonym():
    """'jarvis jarvis google python' -> repeated wake word stripped down
    to 'google python' -> command_parser rewrites to 'search for python'
    -> web_control performs the search."""

    j, voice, fake_speech = make_jarvis(
        listen_side_effect=["jarvis jarvis google python"]
    )

    with patch("web_control.webbrowser.open") as mock_open:
        j.wait_for_wake_word()

    mock_open.assert_called_once_with(
        "https://www.google.com/search?q=python"
    )


def test_pipeline_wake_word_alone_then_command():
    """'jarvis' alone -> JARVIS asks 'Yes?' -> follow-up utterance is
    routed as the command."""

    j, voice, fake_speech = make_jarvis(
        listen_side_effect=["jarvis"],
        listen_with_retry_return="open notepad",
    )

    with patch("system_control.subprocess.Popen") as mock_popen:
        j.wait_for_wake_word()

    mock_popen.assert_called_once_with(["notepad.exe"], shell=False)
    assert "Yes?" in voice.spoken


def test_pipeline_no_wake_word_does_nothing():
    j, voice, fake_speech = make_jarvis(
        listen_side_effect=["open chrome without the wake word"]
    )

    with patch("web_control.webbrowser.open") as mock_open:
        j.wait_for_wake_word()

    mock_open.assert_not_called()
    assert voice.spoken == []


def test_pipeline_accidental_substring_word_does_not_activate():
    """'jarvison' contains 'jarvis' as a substring but must not trigger
    wake-word activation or any action."""

    j, voice, fake_speech = make_jarvis(
        listen_side_effect=["jarvison is not a real word"]
    )

    with patch("web_control.webbrowser.open") as mock_open, \
         patch("system_control.subprocess.Popen") as mock_popen:
        j.wait_for_wake_word()

    mock_open.assert_not_called()
    mock_popen.assert_not_called()
    assert voice.spoken == []


def test_pipeline_jervis_alias_activates_normally():
    j, voice, fake_speech = make_jarvis(
        listen_side_effect=["jervis open notepad"]
    )

    with patch("system_control.subprocess.Popen") as mock_popen:
        j.wait_for_wake_word()

    mock_popen.assert_called_once_with(["notepad.exe"], shell=False)


def test_pipeline_lock_computer_is_mocked_not_real():
    """Existing power command must still route correctly - and this
    test proves it never touches the real os.system call."""

    j, voice, fake_speech = make_jarvis(
        listen_side_effect=["jarvis lock computer"]
    )

    with patch("system_control.os.system") as mock_system:
        j.wait_for_wake_word()

    mock_system.assert_called_once_with(
        "rundll32.exe user32.dll,LockWorkStation"
    )


def test_pipeline_exit_command_stops_the_run_loop():
    j, voice, fake_speech = make_jarvis(
        listen_side_effect=["jarvis exit"]
    )

    j.wait_for_wake_word()

    assert j.running is False
    assert "Goodbye" in voice.spoken[-1]


def test_pipeline_window_control_uses_mocked_ctypes_not_real_window():
    j, voice, fake_speech = make_jarvis(
        listen_side_effect=["jarvis minimize this window"]
    )

    with patch("window_control.user32.GetForegroundWindow", return_value=1), \
         patch("window_control.user32.ShowWindow") as mock_show:
        j.wait_for_wake_word()

    mock_show.assert_called_once()


# =======================================================================
# PHASE 10.3: end-to-end conversational context, across two separate
# wake-word activations (each still requires re-saying "Jarvis" - the
# context layer does not change wake-word behavior). All actual
# browser/system actions are mocked; no real browser ever opens.
# =======================================================================

def test_pipeline_search_youtube_then_wake_word_reply_reaches_search():
    """'jarvis search youtube' -> JARVIS asks 'What should I search
    for?' -> second wake-word activation ('jarvis' alone -> 'Yes?' ->
    'Spider-Man') -> the existing, unchanged web_control search path is
    reached, fully mocked."""
    j, voice, fake_speech = make_jarvis(
        listen_side_effect=["jarvis search youtube", "jarvis"],
        listen_with_retry_return="Spider-Man",
    )

    with patch.object(config, "ENABLE_CONTEXT_LAYER", True), \
         patch.object(config, "ENABLE_INTENT_FALLBACK_LAYER", True), \
         patch("web_control.webbrowser.open") as mock_open:

        j.wait_for_wake_word()
        assert voice.spoken[-1] == "What should I search for?"

        j.wait_for_wake_word()

    assert "Yes?" in voice.spoken
    mock_open.assert_called_once_with(
        "https://www.google.com/search?q=spider-man"
    )
    assert "Searching for spider-man." in voice.spoken
    assert j.commands._pending_slot is None


def test_pipeline_search_youtube_context_disabled_never_opens_browser():
    """Same scenario with the context layer at its default (off) - the
    follow-up reply is never solicited, and no browser action of any
    kind occurs for the ambiguous "search youtube" utterance."""
    j, voice, fake_speech = make_jarvis(
        listen_side_effect=["jarvis search youtube"]
    )

    with patch("web_control.webbrowser.open") as mock_open, \
         patch("web_control.os.path.exists", return_value=False):
        j.wait_for_wake_word()

    mock_open.assert_not_called()


# =======================================================================
# PHASE 10.4: end-to-end contextual reference resolution ("it"/"that"/
# "this" -> the last-named application), across two separate wake-word
# activations. All actual browser/window actions are mocked; no real
# browser or window action ever occurs.
# =======================================================================

def test_pipeline_open_chrome_then_close_it_reaches_window_control():
    """'jarvis open chrome' -> second wake-word activation 'jarvis
    close it' -> resolved against the last-named application and
    routed through the existing, unchanged window_control.handle_
    targeted() path, fully mocked."""
    j, voice, fake_speech = make_jarvis(
        listen_side_effect=["jarvis open chrome", "jarvis close it"]
    )

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch("web_control.os.path.exists", return_value=False), \
         patch("web_control.webbrowser.open") as mock_open:
        j.wait_for_wake_word()

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch(
             "window_control.resolve_window_target", return_value=(True, 1)
         ) as mock_resolve, \
         patch("window_control.user32.PostMessageW") as mock_post:
        j.wait_for_wake_word()

    mock_open.assert_called_once_with("https://www.google.com")
    mock_resolve.assert_called_once_with("chrome")
    mock_post.assert_called_once_with(1, window_control.WM_CLOSE, 0, 0)
    assert "Closing Chrome." in voice.spoken


# =======================================================================
# PHASE 10.5: end-to-end repeat-search ("search that again" -> the last
# search query), across two separate wake-word activations. All actual
# browser actions are mocked; no real browser ever opens.
# =======================================================================

def test_pipeline_search_for_cats_then_search_that_again_reaches_search():
    """'jarvis search for cats' -> second wake-word activation 'jarvis
    search that again' -> resolved against the last search query and
    routed through the existing, unchanged web_control.search() path,
    fully mocked."""
    j, voice, fake_speech = make_jarvis(
        listen_side_effect=["jarvis search for cats", "jarvis search that again"]
    )

    with patch.object(config, "ENABLE_REFERENCE_RESOLUTION", True), \
         patch("web_control.webbrowser.open") as mock_open:
        j.wait_for_wake_word()
        j.wait_for_wake_word()

    assert mock_open.call_count == 2
    mock_open.assert_called_with("https://www.google.com/search?q=cats")
    assert voice.spoken.count("Searching for cats.") == 2


# =======================================================================
# PHASE 11.9 (Step 3): wake-word-omission recovery, end-to-end via the
# real Jarvis.wait_for_wake_word() -> Jarvis._maybe_recover_omitted_
# wake_word() -> jarvis.resolve_wake_word_omission() -> (on explicit
# "yes") CommandProcessor.process() path. All real actions mocked.
# =======================================================================

def test_pipeline_wake_word_omission_tolerance_confirms_and_executes():
    """The exact live-observed Phase 11.8 TEST 9 scenario: "jarvis time
    kya hai" transcribed as "time kya hai" (wake word dropped). With
    the flag on and an explicit "yes" reply, the command actually
    executes through the real information handler."""
    j, voice, fake_speech = make_jarvis(
        listen_side_effect=["time kya hai"],
        listen_with_retry_return="yes",
    )

    with patch.object(config, "ENABLE_WAKE_WORD_OMISSION_TOLERANCE", True):
        j.wait_for_wake_word()

    assert "Did you mean: what time is it? Say yes to confirm." in voice.spoken
    assert any("current time is" in s.lower() for s in voice.spoken)


def test_pipeline_wake_word_omission_default_off_stays_completely_silent():
    """With the flag at its default (False), a wake-word-omitted
    utterance that WOULD have been recoverable produces zero spoken
    output and zero action - byte-for-byte the same as before Phase
    11.9, the same as it did during the actual Phase 11.8 live
    session."""
    j, voice, fake_speech = make_jarvis(listen_side_effect=["time kya hai"])

    j.wait_for_wake_word()

    assert voice.spoken == []


def test_pipeline_wake_word_omission_declined_reply_never_executes():
    j, voice, fake_speech = make_jarvis(
        listen_side_effect=["time kya hai"],
        listen_with_retry_return="",
    )

    with patch.object(config, "ENABLE_WAKE_WORD_OMISSION_TOLERANCE", True):
        j.wait_for_wake_word()

    assert "Did you mean: what time is it? Say yes to confirm." in voice.spoken
    assert "Okay, never mind." in voice.spoken
    assert not any("current time is" in s.lower() for s in voice.spoken)


def test_pipeline_wake_word_omission_no_reply_captured_never_executes():
    """listen_with_retry() itself returning "" (nothing heard at all
    for the confirmation reply) must be treated the same as an
    explicit decline - never executed."""
    j, voice, fake_speech = make_jarvis(
        listen_side_effect=["awaaz kam kar do"],
        listen_with_retry_return="",
    )

    with patch.object(config, "ENABLE_WAKE_WORD_OMISSION_TOLERANCE", True), \
         patch("volume_control.input_control.press_key") as mock_press:
        j.wait_for_wake_word()

    mock_press.assert_not_called()


def test_pipeline_second_roman_urdu_live_scenario_confirms_and_executes():
    """The other exact live-observed Phase 11.8 scenario (TEST 5):
    "jarvis volume kam kar do" transcribed as "awaaz kam kar do"."""
    j, voice, fake_speech = make_jarvis(
        listen_side_effect=["awaaz kam kar do"],
        listen_with_retry_return="yes",
    )

    with patch.object(config, "ENABLE_WAKE_WORD_OMISSION_TOLERANCE", True), \
         patch("volume_control.input_control.press_key") as mock_press:
        j.wait_for_wake_word()

    mock_press.assert_called_once()
    assert "Did you mean: volume down? Say yes to confirm." in voice.spoken


def test_pipeline_dangerous_phrase_without_wake_word_never_offered_even_with_tolerance_on():
    """SECURITY-CRITICAL: a dangerous-sounding phrase captured without
    the wake word must NEVER be offered as a "did you mean" prompt, and
    must NEVER call the real dangerous-action primitive - regardless of
    config.ENABLE_WAKE_WORD_OMISSION_TOLERANCE."""
    j, voice, fake_speech = make_jarvis(
        listen_side_effect=["shut down the computer"]
    )

    with patch.object(config, "ENABLE_WAKE_WORD_OMISSION_TOLERANCE", True), \
         patch("system_control.os.system") as mock_system:
        j.wait_for_wake_word()

    mock_system.assert_not_called()
    assert voice.spoken == []


def test_pipeline_wake_word_present_tolerance_on_behavior_unaffected():
    """Turning the flag on must not change ANYTHING about the normal,
    wake-word-present path - the recovery method must not even be
    consulted when the wake word was found."""
    j, voice, fake_speech = make_jarvis(
        listen_side_effect=["jarvis open notepad"]
    )

    with patch.object(config, "ENABLE_WAKE_WORD_OMISSION_TOLERANCE", True), \
         patch("system_control.subprocess.Popen") as mock_popen:
        j.wait_for_wake_word()

    mock_popen.assert_called_once_with(["notepad.exe"], shell=False)
    assert not any("Did you mean" in s for s in voice.spoken)


def test_pipeline_wake_word_omission_unrecognizable_text_stays_silent():
    """Plain background chatter that resolves to nothing must remain
    completely silent, even with the flag on - never a guess."""
    j, voice, fake_speech = make_jarvis(
        listen_side_effect=["thank you very much"]
    )

    with patch.object(config, "ENABLE_WAKE_WORD_OMISSION_TOLERANCE", True):
        j.wait_for_wake_word()

    assert voice.spoken == []


# =======================================================================
# PHASE 11.11 (Step 7/8): wake-word-omission confirmation, end-to-end,
# across the WIDER affirmative-word set (jarvis.
# WAKE_WORD_RECOVERY_CONFIRM_WORDS) - "yeah"/"haan"/"han"/Urdu "جی
# ہاں"/"جی", and explicit rejection of "no"/"nahi"/"نہیں".
# =======================================================================

def test_pipeline_wake_word_omission_confirmed_with_yeah_executes():
    j, voice, fake_speech = make_jarvis(
        listen_side_effect=["time kya hai"],
        listen_with_retry_return="yeah",
    )

    with patch.object(config, "ENABLE_WAKE_WORD_OMISSION_TOLERANCE", True):
        j.wait_for_wake_word()

    assert any("current time is" in s.lower() for s in voice.spoken)


def test_pipeline_wake_word_omission_confirmed_with_haan_executes():
    j, voice, fake_speech = make_jarvis(
        listen_side_effect=["awaaz kam kar do"],
        listen_with_retry_return="haan",
    )

    with patch.object(config, "ENABLE_WAKE_WORD_OMISSION_TOLERANCE", True), \
         patch("volume_control.input_control.press_key") as mock_press:
        j.wait_for_wake_word()

    mock_press.assert_called_once()


def test_pipeline_wake_word_omission_confirmed_with_urdu_ji_haan_executes():
    j, voice, fake_speech = make_jarvis(
        listen_side_effect=["time kya hai"],
        listen_with_retry_return="جی ہاں",
    )

    with patch.object(config, "ENABLE_WAKE_WORD_OMISSION_TOLERANCE", True):
        j.wait_for_wake_word()

    assert any("current time is" in s.lower() for s in voice.spoken)


def test_pipeline_wake_word_omission_confirmed_with_urdu_ji_executes():
    j, voice, fake_speech = make_jarvis(
        listen_side_effect=["time kya hai"],
        listen_with_retry_return="جی",
    )

    with patch.object(config, "ENABLE_WAKE_WORD_OMISSION_TOLERANCE", True):
        j.wait_for_wake_word()

    assert any("current time is" in s.lower() for s in voice.spoken)


def test_pipeline_wake_word_omission_declined_with_no_never_executes():
    j, voice, fake_speech = make_jarvis(
        listen_side_effect=["time kya hai"],
        listen_with_retry_return="no",
    )

    with patch.object(config, "ENABLE_WAKE_WORD_OMISSION_TOLERANCE", True):
        j.wait_for_wake_word()

    assert "Okay, never mind." in voice.spoken
    assert not any("current time is" in s.lower() for s in voice.spoken)


def test_pipeline_wake_word_omission_declined_with_nahi_never_executes():
    j, voice, fake_speech = make_jarvis(
        listen_side_effect=["awaaz kam kar do"],
        listen_with_retry_return="nahi",
    )

    with patch.object(config, "ENABLE_WAKE_WORD_OMISSION_TOLERANCE", True), \
         patch("volume_control.input_control.press_key") as mock_press:
        j.wait_for_wake_word()

    mock_press.assert_not_called()


def test_pipeline_wake_word_omission_declined_with_urdu_nahi_never_executes():
    j, voice, fake_speech = make_jarvis(
        listen_side_effect=["time kya hai"],
        listen_with_retry_return="نہیں",
    )

    with patch.object(config, "ENABLE_WAKE_WORD_OMISSION_TOLERANCE", True):
        j.wait_for_wake_word()

    assert not any("current time is" in s.lower() for s in voice.spoken)
