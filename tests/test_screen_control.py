from unittest.mock import MagicMock, patch

import screen_control


class FakeVoice:
    def __init__(self):
        self.spoken = []

    def speak(self, text):
        self.spoken.append(text)


def test_take_screenshot_command():
    voice = FakeVoice()
    fake_image = MagicMock()

    with patch("screen_control.os.makedirs") as mock_makedirs, \
         patch("screen_control.ImageGrab.grab", return_value=fake_image) as mock_grab:
        handled = screen_control.handle("take screenshot", voice)

    assert handled is True
    mock_makedirs.assert_called_once_with(
        screen_control.SCREENSHOT_DIR, exist_ok=True
    )
    mock_grab.assert_called_once()
    fake_image.save.assert_called_once()


def test_screenshot_bare_word_command():
    voice = FakeVoice()
    fake_image = MagicMock()

    with patch("screen_control.os.makedirs"), \
         patch("screen_control.ImageGrab.grab", return_value=fake_image):
        handled = screen_control.handle("screenshot", voice)

    assert handled is True


def test_capture_screen_command():
    voice = FakeVoice()
    fake_image = MagicMock()

    with patch("screen_control.os.makedirs"), \
         patch("screen_control.ImageGrab.grab", return_value=fake_image):
        handled = screen_control.handle("capture screen", voice)

    assert handled is True


def test_filename_is_timestamped_png_in_screenshot_dir():
    voice = FakeVoice()
    fake_image = MagicMock()

    with patch("screen_control.os.makedirs"), \
         patch("screen_control.ImageGrab.grab", return_value=fake_image):
        path = screen_control.take_screenshot(voice)

    assert path.startswith(screen_control.SCREENSHOT_DIR)
    assert path.endswith(".png")
    assert "screenshot_" in path


def test_no_match_returns_false():
    voice = FakeVoice()

    handled = screen_control.handle("open notepad", voice)

    assert handled is False
    assert voice.spoken == []
