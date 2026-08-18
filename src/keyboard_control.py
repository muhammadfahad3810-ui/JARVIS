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


def press_backspace(voice):

    voice.speak("Pressing Backspace.")

    input_control.press_key(input_control.VK_BACK)


def press_alt_tab(voice):

    voice.speak("Pressing Alt Tab.")

    input_control.press_key_combo(
        input_control.VK_MENU,
        input_control.VK_TAB
    )


def press_ctrl_shift_escape(voice):

    voice.speak("Pressing Control Shift Escape.")

    input_control.press_key_combo(
        input_control.VK_CONTROL,
        input_control.VK_SHIFT,
        input_control.VK_ESCAPE
    )


def cut(voice):

    voice.speak("Cutting.")

    input_control.press_key_combo(
        input_control.VK_CONTROL,
        input_control.VK_KEY_X
    )


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


def scroll_up(voice):

    voice.speak("Scrolling up.")

    input_control.press_key(input_control.VK_PRIOR)


def scroll_down(voice):

    voice.speak("Scrolling down.")

    input_control.press_key(input_control.VK_NEXT)


def handle(command, voice):
    """Try to handle a fixed-keyboard-shortcut command. Returns True if handled.

    Note: "press delete"/"press del" are deliberately NOT recognized
    here or anywhere else in this project - an unconfirmed Delete
    keypress can destructively delete a selected file/text with no
    undo prompt, and this project's existing security tests (see
    tests/test_security.py's test_press_unknown_key_is_not_sent_to_
    keyboard and tests/test_intent_parser.py's test_classify_press_
    unknown_key_is_unknown) document this as a deliberate allow-list
    exclusion, not an oversight. This gap is intentionally preserved.

    Multi-word combo phrases ("press ctrl shift escape", "press alt
    tab", "press ctrl <letter>") are checked before the single-key
    checks below, so a combo is never partially matched by a broader
    single-key substring first.
    """

    if "press ctrl shift escape" in command:
        press_ctrl_shift_escape(voice)
        return True

    if "press alt tab" in command:
        press_alt_tab(voice)
        return True

    if "press ctrl c" in command:
        copy(voice)
        return True

    if "press ctrl v" in command:
        paste(voice)
        return True

    if "press ctrl x" in command:
        cut(voice)
        return True

    if "press ctrl a" in command:
        select_all(voice)
        return True

    if "press ctrl z" in command:
        undo(voice)
        return True

    if "press enter" in command:
        press_enter(voice)
        return True

    if "press escape" in command:
        press_escape(voice)
        return True

    if "press space" in command:
        press_space(voice)
        return True

    if "press backspace" in command:
        press_backspace(voice)
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

    if "scroll up" in command:
        scroll_up(voice)
        return True

    if "scroll down" in command:
        scroll_down(voice)
        return True

    return False
