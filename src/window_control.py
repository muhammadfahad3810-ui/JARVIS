"""Control over windows: the currently focused ("foreground") window by
default, or (Phase 6) a specific, named application's window.

Untargeted commands ("minimize this window", "show desktop", ...) only
ever act on whatever window already has focus, or simulate the same
Alt+Tab / Win+D shortcuts a user could press themselves - unchanged
since Phase 3.

Targeted commands ("minimize chrome", "switch to notepad", ...) - see
handle_targeted() - resolve a spoken application name against the fixed
intent_parser.KNOWN_APPLICATIONS allow-list ONLY. An application name
outside that allow-list is never used to search for or act on any
window - window enumeration is not even attempted in that case (see
resolve_window_target()). If the named application isn't currently
open, this reports that gracefully; it never falls back to acting on
the foreground window instead.
"""

import ctypes

import input_control
import intent_parser

user32 = ctypes.windll.user32

SW_MINIMIZE = 6
SW_MAXIMIZE = 3
SW_RESTORE = 9
WM_CLOSE = 0x0010

# Callback signature for EnumWindows: BOOL CALLBACK(HWND, LPARAM).
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)

# Fixed, hardcoded title hints for matching a known application's window.
# Deliberately NOT derived from user speech in any way - only ever looked
# up by a key that has already been validated against
# intent_parser.KNOWN_APPLICATIONS (see resolve_window_target()). Some
# applications (youtube/google/github) have no standalone top-level
# window and are intentionally left out - targeting them will always
# resolve to "not found", never a guess.
WINDOW_TITLE_HINTS = {
    "chrome": ("chrome",),
    "edge": ("edge",),
    "notepad": ("notepad",),
    "calculator": ("calculator",),
    "command prompt": ("command prompt", "cmd"),
    "cmd": ("command prompt", "cmd"),
    "powershell": ("powershell",),
    "file explorer": ("file explorer", "explorer"),
    "settings": ("settings",),
    "task manager": ("task manager",),
}


def _foreground_window():
    return user32.GetForegroundWindow()


def minimize_window(voice):

    voice.speak("Minimizing the window.")

    hwnd = _foreground_window()

    if hwnd:
        user32.ShowWindow(hwnd, SW_MINIMIZE)


def maximize_window(voice):

    voice.speak("Maximizing the window.")

    hwnd = _foreground_window()

    if hwnd:
        user32.ShowWindow(hwnd, SW_MAXIMIZE)


def restore_window(voice):

    voice.speak("Restoring the window.")

    hwnd = _foreground_window()

    if hwnd:
        user32.ShowWindow(hwnd, SW_RESTORE)


def close_window(voice):

    voice.speak("Closing the window.")

    hwnd = _foreground_window()

    if hwnd:
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)


def switch_window(voice):

    voice.speak("Switching window.")

    input_control.press_key_combo(
        input_control.VK_MENU,
        input_control.VK_TAB
    )


def show_desktop(voice):

    voice.speak("Showing the desktop.")

    input_control.press_key_combo(
        input_control.VK_LWIN,
        input_control.VK_KEY_D
    )


def handle(command, voice):
    """Try to handle a window-control command. Returns True if handled."""

    if "minimize" in command:
        minimize_window(voice)
        return True

    if "maximize" in command:
        maximize_window(voice)
        return True

    if "restore" in command:
        restore_window(voice)
        return True

    if "close" in command and "window" in command:
        close_window(voice)
        return True

    if "next window" in command or ("switch" in command and "window" in command):
        switch_window(voice)
        return True

    if "show desktop" in command:
        show_desktop(voice)
        return True

    return False


# =============================================================
# PHASE 6: TARGETED WINDOW CONTROL (by known application name)
# =============================================================

def _list_visible_window_titles():
    """Return a list of (hwnd, title) for currently visible top-level
    windows with a non-empty title, using only ctypes/user32 - no new
    dependency. This is a low-level primitive: it never filters by
    name itself, and callers must only ever search the result for one
    of the fixed title hints in WINDOW_TITLE_HINTS (see
    find_window_by_application()) - never for arbitrary spoken text.
    """

    windows = []

    def _on_window(hwnd, _lparam):

        if not user32.IsWindowVisible(hwnd):
            return 1

        length = user32.GetWindowTextLengthW(hwnd)

        if length == 0:
            return 1

        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)

        if buffer.value:
            windows.append((hwnd, buffer.value))

        return 1

    user32.EnumWindows(WNDENUMPROC(_on_window), 0)

    return windows


def find_window_by_application(app_name):
    """Find the first visible window whose title matches the fixed
    title hint(s) for `app_name` (see WINDOW_TITLE_HINTS). `app_name`
    is expected to already be a validated intent_parser.KNOWN_APPLICATIONS
    key - this function does not itself reject unknown names (see
    resolve_window_target() for the actual allow-list gate), it simply
    returns None for any name with no configured hint, which happens to
    include every name outside the allow-list too.

    Returns the window handle of the first match, or None. "First
    visible matching window" wins if more than one is open - documented
    behavior, not randomized or asked-about.
    """

    hints = WINDOW_TITLE_HINTS.get(app_name)

    if not hints:
        return None

    for hwnd, title in _list_visible_window_titles():

        lowered = title.lower()

        if any(hint in lowered for hint in hints):
            return hwnd

    return None


def resolve_window_target(app_name):
    """Validate `app_name` against the fixed application allow-list
    (intent_parser.KNOWN_APPLICATIONS) and, only if it's valid, look
    for a matching open window.

    Returns:
        (True, hwnd)  - app_name is known AND a matching window is open.
        (True, None)  - app_name is known but no matching window is
                         currently open. Callers must report this
                         gracefully, never fall back to the foreground
                         window.
        (False, None) - app_name is not in the allow-list at all. Window
                         enumeration is never attempted in this case.
    """

    if app_name not in intent_parser.KNOWN_APPLICATIONS:
        return False, None

    return True, find_window_by_application(app_name)


def _resolve_and_report(app_name, voice):
    """Shared allow-list validation + "not found" reporting for the
    by-name action functions below. Returns a window handle to act on,
    or None if the caller should do nothing further (either the name
    isn't known, or it's known but not currently open - either way,
    this never returns the foreground window as a fallback)."""

    is_known, hwnd = resolve_window_target(app_name)

    display_name = app_name.title()

    if not is_known:
        voice.speak(f"I don't know an application called {display_name}.")
        return None

    if hwnd is None:
        voice.speak(f"I couldn't find an open {display_name} window.")
        return None

    return hwnd


def minimize_window_by_name(app_name, voice):

    hwnd = _resolve_and_report(app_name, voice)

    if hwnd is None:
        return

    voice.speak(f"Minimizing {app_name.title()}.")

    user32.ShowWindow(hwnd, SW_MINIMIZE)


def maximize_window_by_name(app_name, voice):

    hwnd = _resolve_and_report(app_name, voice)

    if hwnd is None:
        return

    voice.speak(f"Maximizing {app_name.title()}.")

    user32.ShowWindow(hwnd, SW_MAXIMIZE)


def restore_window_by_name(app_name, voice):

    hwnd = _resolve_and_report(app_name, voice)

    if hwnd is None:
        return

    voice.speak(f"Restoring {app_name.title()}.")

    user32.ShowWindow(hwnd, SW_RESTORE)


def close_window_by_name(app_name, voice):

    hwnd = _resolve_and_report(app_name, voice)

    if hwnd is None:
        return

    voice.speak(f"Closing {app_name.title()}.")

    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)


def switch_to_window_by_name(app_name, voice):

    hwnd = _resolve_and_report(app_name, voice)

    if hwnd is None:
        return

    voice.speak(f"Switching to {app_name.title()}.")

    # Restore first in case it's minimized, then bring it to the front.
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetForegroundWindow(hwnd)


def _find_known_application_in(command):
    """Return the first intent_parser.KNOWN_APPLICATIONS key found as a
    substring of `command`, or None. This is the ONLY way a target
    application name ever enters this module - always checked against
    the fixed allow-list, never treated as arbitrary window-title text
    taken directly from speech."""

    for name in intent_parser.KNOWN_APPLICATIONS:

        if name in command:
            return name

    return None


def handle_targeted(command, voice):
    """Try to handle a window-control command that names a specific,
    known application (e.g. "minimize chrome", "switch to notepad",
    "close the notepad window").

    Returns True if handled - including a graceful "couldn't find" or
    "don't know that application" response - False if the command
    doesn't name a known application at all, in which case the caller
    should fall back to the existing untargeted handle() above.

    Must be checked BEFORE web_control.handle()/system_control's
    application handling in the dispatch chain: e.g. "close chrome"
    would otherwise be caught by web_control's bare "chrome" substring
    check, which only knows how to OPEN Chrome, not close a specific
    window.
    """

    app_name = _find_known_application_in(command)

    if app_name is None:
        return False

    if "minimize" in command:
        minimize_window_by_name(app_name, voice)
        return True

    if "maximize" in command:
        maximize_window_by_name(app_name, voice)
        return True

    if "restore" in command:
        restore_window_by_name(app_name, voice)
        return True

    if "close" in command:
        close_window_by_name(app_name, voice)
        return True

    if "switch" in command:
        switch_to_window_by_name(app_name, voice)
        return True

    return False
