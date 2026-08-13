"""Deterministic intent classification - a fixed, closed allow-list of
supported intents, built on top of command_parser.normalize().

This is a SAFE layer by construction:

- classify() only ever returns one of the fixed Intent values below.
  Anything not explicitly recognized is Intent.UNKNOWN - there is no
  fuzzy/fallback matching that could turn arbitrary speech into a
  command.
- OPEN_APPLICATION targets only ever come from the fixed
  KNOWN_APPLICATIONS allow-list. An application name JARVIS doesn't
  know about is never returned as a target - the whole command is
  UNKNOWN instead.
- PRESS_KEY targets only ever come from the fixed KNOWN_KEYS allow-list
  (enter/escape/space/tab), matching keyboard_control.py's fixed
  shortcut set exactly. No arbitrary text is ever treated as a key.
- SEARCH's target is the literal search query text - this is safe
  because it is only ever URL-encoded into a Google search link
  (see web_control.search()), never executed as code, a shell command,
  or typed as keystrokes.
- to_canonical_command() only ever renders back one of a fixed set of
  literal strings (or a search URL-safe query) - it cannot construct an
  arbitrary command from user input.

No LLM or external AI service is used here - classification is plain
deterministic string matching.

Note on how this is wired into commands.py: by the time text reaches
here, command_parser.normalize() has already rewritten essentially all
of the natural-language variations this project supports into their
canonical form, so classify()/to_canonical_command() round-trips to an
identical string for every already-supported command - this module is
currently used for diagnostics (config.DEBUG) and as a directly testable
allow-list boundary, not as a second dispatch path, specifically so it
can never change behavior for any command that already works.
"""

import re


class Intent:
    OPEN_APPLICATION = "OPEN_APPLICATION"
    SEARCH = "SEARCH"
    VOLUME_UP = "VOLUME_UP"
    VOLUME_DOWN = "VOLUME_DOWN"
    SET_VOLUME = "SET_VOLUME"
    MUTE = "MUTE"
    UNMUTE = "UNMUTE"
    MINIMIZE_WINDOW = "MINIMIZE_WINDOW"
    MAXIMIZE_WINDOW = "MAXIMIZE_WINDOW"
    RESTORE_WINDOW = "RESTORE_WINDOW"
    CLOSE_WINDOW = "CLOSE_WINDOW"
    SWITCH_WINDOW = "SWITCH_WINDOW"
    SHOW_DESKTOP = "SHOW_DESKTOP"
    PLAY_PAUSE = "PLAY_PAUSE"
    NEXT_TRACK = "NEXT_TRACK"
    PREVIOUS_TRACK = "PREVIOUS_TRACK"
    SCREENSHOT = "SCREENSHOT"
    PRESS_KEY = "PRESS_KEY"
    COPY = "COPY"
    PASTE = "PASTE"
    SELECT_ALL = "SELECT_ALL"
    UNDO = "UNDO"
    TIME = "TIME"
    DATE = "DATE"
    UNKNOWN = "UNKNOWN"


# Fixed allow-list: application/website name -> canonical command.
# classify() never returns an OPEN_APPLICATION target outside this list.
KNOWN_APPLICATIONS = {
    "chrome": "open chrome",
    "edge": "open edge",
    "youtube": "open youtube",
    "google": "open google",
    "github": "open github",
    "notepad": "open notepad",
    "calculator": "open calculator",
    "command prompt": "open command prompt",
    "cmd": "open cmd",
    "powershell": "open powershell",
    "file explorer": "open file explorer",
    "settings": "open settings",
    "task manager": "open task manager",
}

# Fixed allow-list of keys for PRESS_KEY - mirrors keyboard_control.py's
# fixed shortcut set exactly. Never arbitrary text.
KNOWN_KEYS = ["enter", "escape", "space", "tab"]

# Phase 7: matches the canonical "set volume to <N>" string
# command_parser.canonicalize_set_volume_phrase() produces - N is
# already guaranteed 0-100 by that function, but the range is
# re-checked below anyway (never trust a single validation point).
SET_VOLUME_RE = re.compile(r"^set volume to (\d{1,3})$")


class IntentResult:
    """A classified intent plus an optional target, both drawn only from
    fixed allow-lists (see module docstring)."""

    __slots__ = ("intent", "target")

    def __init__(self, intent, target=None):
        self.intent = intent
        self.target = target

    def __eq__(self, other):
        return (
            isinstance(other, IntentResult)
            and self.intent == other.intent
            and self.target == other.target
        )

    def __repr__(self):
        return f"IntentResult({self.intent!r}, target={self.target!r})"


UNKNOWN_RESULT = IntentResult(Intent.UNKNOWN)


def classify(text):
    """Classify already-normalized text into a fixed Intent (+ optional
    target). Returns Intent.UNKNOWN for anything not explicitly
    recognized - this is a closed allow-list, not a fuzzy classifier."""

    if not text:
        return UNKNOWN_RESULT

    # SCREENSHOT
    if "screenshot" in text or ("capture" in text and "screen" in text):
        return IntentResult(Intent.SCREENSHOT)

    # WINDOW CONTROL
    if "minimize" in text:
        return IntentResult(Intent.MINIMIZE_WINDOW)

    if "maximize" in text:
        return IntentResult(Intent.MAXIMIZE_WINDOW)

    if "restore" in text:
        return IntentResult(Intent.RESTORE_WINDOW)

    if "close" in text and "window" in text:
        return IntentResult(Intent.CLOSE_WINDOW)

    if "show" in text and "desktop" in text:
        return IntentResult(Intent.SHOW_DESKTOP)

    if "switch" in text and "window" in text:
        return IntentResult(Intent.SWITCH_WINDOW)

    # MEDIA
    if "skip" in text or (
        "next" in text and ("track" in text or "song" in text)
    ):
        return IntentResult(Intent.NEXT_TRACK)

    if "previous" in text and ("track" in text or "song" in text):
        return IntentResult(Intent.PREVIOUS_TRACK)

    if "play" in text or "pause" in text:
        return IntentResult(Intent.PLAY_PAUSE)

    # VOLUME
    if "unmute" in text:
        return IntentResult(Intent.UNMUTE)

    if "mute" in text:
        return IntentResult(Intent.MUTE)

    set_volume_match = SET_VOLUME_RE.match(text)

    if set_volume_match:
        percent = int(set_volume_match.group(1))

        if 0 <= percent <= 100:
            return IntentResult(Intent.SET_VOLUME, target=percent)

        return UNKNOWN_RESULT

    if "volume" in text and "up" in text:
        return IntentResult(Intent.VOLUME_UP)

    if "volume" in text and "down" in text:
        return IntentResult(Intent.VOLUME_DOWN)

    # KEYBOARD
    if "select all" in text:
        return IntentResult(Intent.SELECT_ALL)

    if "copy" in text:
        return IntentResult(Intent.COPY)

    if "paste" in text:
        return IntentResult(Intent.PASTE)

    if "undo" in text:
        return IntentResult(Intent.UNDO)

    for key in KNOWN_KEYS:
        if f"press {key}" in text:
            return IntentResult(Intent.PRESS_KEY, target=key)

    # SEARCH - target is free-text but only ever used as a URL-encoded
    # search query (see module docstring), never executed.
    if text.startswith("search for"):
        query = text.replace("search for", "", 1).strip()
        return IntentResult(Intent.SEARCH, target=query)

    # APPLICATIONS / WEBSITES - target only from the fixed allow-list.
    for name in KNOWN_APPLICATIONS:
        if name in text:
            return IntentResult(Intent.OPEN_APPLICATION, target=name)

    # INFO
    if "date" in text:
        return IntentResult(Intent.DATE)

    if "time" in text:
        return IntentResult(Intent.TIME)

    return UNKNOWN_RESULT


def to_canonical_command(result):
    """Render an IntentResult back into the canonical command string the
    existing handler modules already understand. Returns None for
    UNKNOWN (callers should keep using whatever text they already have).

    This can only ever produce one of a fixed set of literal strings (or
    a 'search for <query>' string built from the already-safe SEARCH
    target) - it cannot construct an arbitrary command.
    """

    intent = result.intent
    target = result.target

    if intent == Intent.OPEN_APPLICATION:
        return KNOWN_APPLICATIONS.get(target)

    if intent == Intent.SEARCH:
        return f"search for {target}".strip()

    if intent == Intent.SCREENSHOT:
        return "screenshot"

    if intent == Intent.MINIMIZE_WINDOW:
        return "minimize this window"

    if intent == Intent.MAXIMIZE_WINDOW:
        return "maximize this window"

    if intent == Intent.RESTORE_WINDOW:
        return "restore this window"

    if intent == Intent.CLOSE_WINDOW:
        return "close this window"

    if intent == Intent.SWITCH_WINDOW:
        return "switch window"

    if intent == Intent.SHOW_DESKTOP:
        return "show desktop"

    if intent == Intent.PLAY_PAUSE:
        return "play"

    if intent == Intent.NEXT_TRACK:
        return "next track"

    if intent == Intent.PREVIOUS_TRACK:
        return "previous track"

    if intent == Intent.VOLUME_UP:
        return "volume up"

    if intent == Intent.VOLUME_DOWN:
        return "volume down"

    if intent == Intent.SET_VOLUME:
        if isinstance(target, int) and not isinstance(target, bool) and 0 <= target <= 100:
            return f"set volume to {target}"
        return None

    if intent == Intent.MUTE:
        return "mute"

    if intent == Intent.UNMUTE:
        return "unmute"

    if intent == Intent.PRESS_KEY:
        if target in KNOWN_KEYS:
            return f"press {target}"
        return None

    if intent == Intent.COPY:
        return "copy"

    if intent == Intent.PASTE:
        return "paste"

    if intent == Intent.SELECT_ALL:
        return "select all"

    if intent == Intent.UNDO:
        return "undo"

    if intent == Intent.DATE:
        return "what is the date"

    if intent == Intent.TIME:
        return "what time is it"

    return None
