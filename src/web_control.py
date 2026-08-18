import os
import re
import subprocess
import webbrowser

import input_control


CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

EDGE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def open_chrome(voice):

    voice.speak("Opening Chrome.")

    for path in CHROME_PATHS:

        if os.path.exists(path):

            subprocess.Popen(
                [path],
                shell=False
            )

            return

    webbrowser.open(
        "https://www.google.com"
    )


def open_edge(voice):

    voice.speak("Opening Edge.")

    for path in EDGE_PATHS:

        if os.path.exists(path):

            subprocess.Popen(
                [path],
                shell=False
            )

            return

    webbrowser.open(
        "https://www.bing.com"
    )


def open_youtube(voice):

    voice.speak("Opening YouTube.")

    webbrowser.open(
        "https://www.youtube.com"
    )


def open_google(voice):

    voice.speak("Opening Google.")

    webbrowser.open(
        "https://www.google.com"
    )


def open_github(voice):

    voice.speak("Opening GitHub.")

    webbrowser.open(
        "https://github.com"
    )


def search(voice, query):

    voice.speak(
        f"Searching for {query}."
    )

    url = (
        "https://www.google.com/search?q="
        + query.replace(" ", "+")
    )

    webbrowser.open(url)


# Spoken when a fixed-shortcut action below reports its low-level
# SendInput injection was rejected by the OS (see input_control.py's
# module docstring - e.g. UIPI blocking input into a higher-privilege
# window). Deliberately generic (never names what was attempted) and
# never speaks the SUCCESS message in this case - see each function
# below: the action is performed FIRST, then the spoken response is
# chosen from its real, checked outcome, rather than always claiming
# success up front.
INPUT_FAILURE_MESSAGE = "I couldn't send that command."


def refresh(voice):

    ok = input_control.press_key(input_control.VK_F5)

    voice.speak("Refreshing." if ok else INPUT_FAILURE_MESSAGE)


def new_tab(voice):

    ok = input_control.press_key_combo(
        input_control.VK_CONTROL,
        input_control.VK_KEY_T
    )

    voice.speak("Opening new tab." if ok else INPUT_FAILURE_MESSAGE)


def close_tab(voice):

    ok = input_control.press_key_combo(
        input_control.VK_CONTROL,
        input_control.VK_KEY_W
    )

    voice.speak("Closing tab." if ok else INPUT_FAILURE_MESSAGE)


def next_tab(voice):

    ok = input_control.press_key_combo(
        input_control.VK_CONTROL,
        input_control.VK_TAB
    )

    voice.speak("Switching to the next tab." if ok else INPUT_FAILURE_MESSAGE)


def previous_tab(voice):

    ok = input_control.press_key_combo(
        input_control.VK_CONTROL,
        input_control.VK_SHIFT,
        input_control.VK_TAB
    )

    voice.speak(
        "Switching to the previous tab." if ok else INPUT_FAILURE_MESSAGE
    )


def go_back(voice):

    ok = input_control.press_key_combo(
        input_control.VK_MENU,
        input_control.VK_LEFT
    )

    voice.speak("Going back." if ok else INPUT_FAILURE_MESSAGE)


def go_forward(voice):

    ok = input_control.press_key_combo(
        input_control.VK_MENU,
        input_control.VK_RIGHT
    )

    voice.speak("Going forward." if ok else INPUT_FAILURE_MESSAGE)


# Word-boundary-anchored ("\bback\b") rather than a bare substring
# check: "press backspace" contains "back" as a literal substring
# (backspace = "back" + "space"), and a bare `"back" in command` check
# would incorrectly hijack it into a browser "go back" action before
# keyboard_control.handle() ever gets a chance to handle it as the
# Backspace key. Word-boundary matching means "back" only matches as
# its own standalone word, never as a prefix fragment of "backspace".
_BACK_PATTERN = re.compile(r"\bback\b")

# "new <browser name> tab" - the browser/app name sits BETWEEN "new"
# and "tab" ("open a new chrome tab"), unlike the more common "new tab"
# contiguous phrase already covered by the plain substring check below.
# Explicit, hand-enumerated literal aliases - not an open-ended regex -
# matching this project's existing "enumerate the variant" style (see
# intent_parser.KNOWN_APPLICATIONS, multilingual_normalizer's marker
# tuples) rather than a broad "new .* tab" pattern that could match
# unrelated phrasing far apart in a longer sentence.
NEW_TAB_ALIASES = ("new tab", "new chrome tab", "new browser tab", "new edge tab")

# "close (the|this|a|new)* tab" - tolerates the small, fixed set of
# articles/qualifiers a speaker naturally inserts between "close" and
# "tab" ("close the tab", "close this tab", "close the new tab").
# Deliberately a bounded, enumerated word class repeated with `*`, NOT
# an open "\bclose\b.*\btab\b" that could span an entire unrelated
# sentence - mirrors intent_layer.py's own _DANGEROUS_ARTICLE pattern
# (same "optional article between verb and noun" reasoning, same small
# fixed word list). Checked BEFORE NEW_TAB_ALIASES below: "close the
# new tab" contains the literal substring "new tab" too, but closing is
# what the user actually asked for - the more specific, verb-led match
# must win.
_TAB_ARTICLE = r"(?:(?:the|this|a|new)\s+)*"
CLOSE_TAB_RE = re.compile(r"\bclose\b\s+" + _TAB_ARTICLE + r"tab\b")


def handle(command, voice):
    """Try to handle a web-related command. Returns True if handled."""

    # YOUTUBE
    if "open youtube" in command:
        open_youtube(voice)
        return True

    # GOOGLE
    if "open google" in command:
        open_google(voice)
        return True

    # GITHUB
    if "open github" in command:
        open_github(voice)
        return True

    # SEARCH
    if command.startswith("search for"):

        query = command.replace(
            "search for",
            "",
            1
        ).strip()

        if query:
            search(voice, query)

        return True

    # BROWSER TAB MANAGEMENT - checked before the generic CHROME/EDGE
    # open checks below (no overlap in practice, since none of these
    # phrases contain "chrome"/"edge"), and before keyboard_control.
    # handle()'s "press tab" check ever gets a chance to run (this
    # module is earlier in commands.py's dispatch chain) - so "open new
    # tab"/"close the tab"/"tab band karo" (routed here via
    # multilingual_normalizer, see that module's _check_tab_browser())
    # can never be mistaken for the bare Tab key. CLOSE_TAB_RE is
    # checked FIRST, before NEW_TAB_ALIASES: "close the new tab"
    # contains the literal substring "new tab", but the verb "close"
    # makes the intent unambiguous and must win (Phase 11.12 fix - see
    # CLOSE_TAB_RE's own comment above).
    if CLOSE_TAB_RE.search(command):
        close_tab(voice)
        return True

    if any(alias in command for alias in NEW_TAB_ALIASES):
        new_tab(voice)
        return True

    if "next tab" in command:
        next_tab(voice)
        return True

    if "previous tab" in command:
        previous_tab(voice)
        return True

    # BROWSER NAVIGATION
    if "refresh" in command or "reload" in command:
        refresh(voice)
        return True

    if "go forward" in command:
        go_forward(voice)
        return True

    if _BACK_PATTERN.search(command):
        go_back(voice)
        return True

    # CHROME
    if "chrome" in command:
        open_chrome(voice)
        return True

    # EDGE
    if "edge" in command:
        open_edge(voice)
        return True

    return False
