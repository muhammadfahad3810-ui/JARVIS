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

import jarvis as jarvis_module


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
