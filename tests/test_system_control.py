from unittest.mock import patch

import system_control


class FakeVoice:
    def __init__(self):
        self.spoken = []

    def speak(self, text):
        self.spoken.append(text)


def test_handle_application_notepad():
    voice = FakeVoice()

    with patch("system_control.subprocess.Popen") as mock_popen:
        handled = system_control.handle_application("open notepad", voice)

    assert handled is True
    mock_popen.assert_called_once_with(["notepad.exe"], shell=False)


def test_handle_application_calculator_short_form():
    voice = FakeVoice()

    with patch("system_control.subprocess.Popen") as mock_popen:
        handled = system_control.handle_application("open calc", voice)

    assert handled is True
    mock_popen.assert_called_once_with(["calc.exe"], shell=False)


def test_handle_application_command_prompt_requires_exact_cmd():
    voice = FakeVoice()

    with patch("system_control.subprocess.Popen") as mock_popen:
        handled = system_control.handle_application("cmd", voice)

    assert handled is True
    mock_popen.assert_called_once_with(["cmd.exe"], shell=False)


def test_handle_application_command_prompt_phrase():
    voice = FakeVoice()

    with patch("system_control.subprocess.Popen") as mock_popen:
        handled = system_control.handle_application("open command prompt", voice)

    assert handled is True
    mock_popen.assert_called_once_with(["cmd.exe"], shell=False)


def test_handle_application_powershell():
    voice = FakeVoice()

    with patch("system_control.subprocess.Popen") as mock_popen:
        handled = system_control.handle_application("open powershell", voice)

    assert handled is True
    mock_popen.assert_called_once_with(["powershell.exe"], shell=False)


def test_handle_application_settings():
    voice = FakeVoice()

    with patch("system_control.subprocess.Popen") as mock_popen:
        handled = system_control.handle_application("open settings", voice)

    assert handled is True
    mock_popen.assert_called_once_with(
        ["cmd", "/c", "start", "ms-settings:"], shell=False
    )


def test_handle_application_task_manager():
    voice = FakeVoice()

    with patch("system_control.subprocess.Popen") as mock_popen:
        handled = system_control.handle_application("open task manager", voice)

    assert handled is True
    mock_popen.assert_called_once_with(["taskmgr.exe"], shell=False)


def test_handle_application_no_match_returns_false():
    voice = FakeVoice()

    handled = system_control.handle_application("play music", voice)

    assert handled is False
    assert voice.spoken == []


def test_handle_system_lock_computer():
    voice = FakeVoice()

    with patch("system_control.os.system") as mock_system:
        handled = system_control.handle_system("lock computer", voice)

    assert handled is True
    mock_system.assert_called_once_with("rundll32.exe user32.dll,LockWorkStation")


def test_handle_system_shutdown_computer():
    voice = FakeVoice()

    with patch("system_control.os.system") as mock_system:
        handled = system_control.handle_system("shutdown computer", voice)

    assert handled is True
    mock_system.assert_called_once_with("shutdown /s /t 5")


def test_handle_system_restart_computer():
    voice = FakeVoice()

    with patch("system_control.os.system") as mock_system:
        handled = system_control.handle_system("restart computer", voice)

    assert handled is True
    mock_system.assert_called_once_with("shutdown /r /t 5")


def test_handle_system_no_match_returns_false():
    voice = FakeVoice()

    handled = system_control.handle_system("open notepad", voice)

    assert handled is False
