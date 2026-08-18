"""Fixed, safe keyboard shortcuts only.

This is NOT arbitrary voice-to-keyboard injection: JARVIS never types
spoken text. Only the specific hardcoded keys/combos below can ever be
sent, each triggered by an exact, fixed voice phrase.
"""

import input_control


def press_enter(voice):

    input_control.press_key(input_control.VK_RETURN)

    voice.speak("Pressing Enter.")


def press_escape(voice):

    input_control.press_key(input_control.VK_ESCAPE)

    voice.speak("Pressing Escape.")


def press_space(voice):

    input_control.press_key(input_control.VK_SPACE)

    voice.speak("Pressing Space.")


def press_tab(voice):

    input_control.press_key(input_control.VK_TAB)

    voice.speak("Pressing Tab.")


def press_backspace(voice):

    input_control.press_key(input_control.VK_BACK)

    voice.speak("Pressing Backspace.")


def press_alt_tab(voice):

    input_control.press_key_combo(
        input_control.VK_MENU,
        input_control.VK_TAB
    )

    voice.speak("Pressing Alt Tab.")


def press_ctrl_shift_escape(voice):

    input_control.press_key_combo(
        input_control.VK_CONTROL,
        input_control.VK_SHIFT,
        input_control.VK_ESCAPE
    )

    voice.speak("Pressing Control Shift Escape.")


def cut(voice):

    input_control.press_key_combo(
        input_control.VK_CONTROL,
        input_control.VK_KEY_X
    )

    voice.speak("Cutting.")


def copy(voice):

    input_control.press_key_combo(
        input_control.VK_CONTROL,
        input_control.VK_KEY_C
    )

    voice.speak("Copying.")


def paste(voice):

    input_control.press_key_combo(
        input_control.VK_CONTROL,
        input_control.VK_KEY_V
    )

    voice.speak("Pasting.")


def select_all(voice):

    input_control.press_key_combo(
        input_control.VK_CONTROL,
        input_control.VK_KEY_A
    )

    voice.speak("Selecting all.")


def undo(voice):

    input_control.press_key_combo(
        input_control.VK_CONTROL,
        input_control.VK_KEY_Z
    )

    voice.speak("Undoing.")


def scroll_up(voice):

    input_control.press_key(input_control.VK_PRIOR)

    voice.speak("Scrolling up.")


def scroll_down(voice):

    input_control.press_key(input_control.VK_NEXT)

    voice.speak("Scrolling down.")


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
