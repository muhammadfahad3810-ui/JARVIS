"""Fixed, safe keyboard shortcuts only.

This is NOT arbitrary voice-to-keyboard injection: JARVIS never types
spoken text. Only the specific hardcoded keys/combos below can ever be
sent, each triggered by an exact, fixed voice phrase.
"""

import input_control


def press_enter(voice):

    voice.speak("Pressing Enter.")

    input_control.press_key(input_control.VK_RETURN)


def press_escape(voice):

    voice.speak("Pressing Escape.")

    input_control.press_key(input_control.VK_ESCAPE)


def press_space(voice):

    voice.speak("Pressing Space.")

    input_control.press_key(input_control.VK_SPACE)


def press_tab(voice):

    voice.speak("Pressing Tab.")

    input_control.press_key(input_control.VK_TAB)


def copy(voice):

    voice.speak("Copying.")

    input_control.press_key_combo(
        input_control.VK_CONTROL,
        input_control.VK_KEY_C
    )


def paste(voice):

    voice.speak("Pasting.")

    input_control.press_key_combo(
        input_control.VK_CONTROL,
        input_control.VK_KEY_V
    )


def select_all(voice):

    voice.speak("Selecting all.")

    input_control.press_key_combo(
        input_control.VK_CONTROL,
        input_control.VK_KEY_A
    )


def undo(voice):

    voice.speak("Undoing.")

    input_control.press_key_combo(
        input_control.VK_CONTROL,
        input_control.VK_KEY_Z
    )


def handle(command, voice):
    """Try to handle a fixed-keyboard-shortcut command. Returns True if handled."""

    if "press enter" in command:
        press_enter(voice)
        return True

    if "press escape" in command:
        press_escape(voice)
        return True

    if "press space" in command:
        press_space(voice)
        return True

    if "press tab" in command:
        press_tab(voice)
        return True

    if "select all" in command:
        select_all(voice)
        return True

    if "copy" in command:
        copy(voice)
        return True

    if "paste" in command:
        paste(voice)
        return True

    if "undo" in command:
        undo(voice)
        return True

    return False
