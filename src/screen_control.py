"""Screenshot capture, saved to a dedicated project-controlled directory."""

import datetime
import os

from PIL import ImageGrab

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCREENSHOT_DIR = os.path.join(PROJECT_ROOT, "screenshots")


def take_screenshot(voice):

    voice.speak("Taking a screenshot.")

    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    # Microsecond precision avoids overwriting a previous screenshot if
    # this is called more than once within the same second.
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"screenshot_{timestamp}.png"
    path = os.path.join(SCREENSHOT_DIR, filename)

    image = ImageGrab.grab()
    image.save(path)

    return path


def handle(command, voice):
    """Try to handle a screenshot command. Returns True if handled."""

    if (
        "screenshot" in command
        or "capture screen" in command
        or "capture the screen" in command
    ):
        take_screenshot(voice)
        return True

    return False
