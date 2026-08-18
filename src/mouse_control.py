"""Fixed, safe mouse actions only.

Like keyboard_control.py, this is NOT arbitrary automation: only the
specific hardcoded actions below (click, double-click, right-click, and
a small fixed-pixel-distance cursor nudge) can ever be triggered, each
by an exact, fixed voice phrase. Movement distance is a fixed constant
(MOVE_STEP_PIXELS) - never a value derived from spoken text.
"""

import input_control

MOVE_STEP_PIXELS = 50


def click(voice):

    voice.speak("Clicking.")

    input_control.click_mouse()


def double_click(voice):

    voice.speak("Double clicking.")

    input_control.click_mouse()
    input_control.click_mouse()


def right_click(voice):

    voice.speak("Right clicking.")

    input_control.right_click_mouse()


def move_left(voice):

    voice.speak("Moving left.")

    input_control.move_mouse_by(-MOVE_STEP_PIXELS, 0)


def move_right(voice):

    voice.speak("Moving right.")

    input_control.move_mouse_by(MOVE_STEP_PIXELS, 0)


def move_up(voice):

    voice.speak("Moving up.")

    input_control.move_mouse_by(0, -MOVE_STEP_PIXELS)


def move_down(voice):

    voice.speak("Moving down.")

    input_control.move_mouse_by(0, MOVE_STEP_PIXELS)


def handle(command, voice):
    """Try to handle a mouse command. Returns True if handled.

    "double click"/"right click" are checked before the bare "click"
    check below, since both contain "click" as a substring - the more
    specific phrase must win. "left click" is deliberately NOT its own
    branch: it already contains "click" and correctly falls through to
    the same bare-click handling as plain "click".
    """

    if "double click" in command:
        double_click(voice)
        return True

    if "right click" in command:
        right_click(voice)
        return True

    if "click" in command:
        click(voice)
        return True

    if "move left" in command:
        move_left(voice)
        return True

    if "move right" in command:
        move_right(voice)
        return True

    if "move up" in command:
        move_up(voice)
        return True

    if "move down" in command:
        move_down(voice)
        return True

    return False
