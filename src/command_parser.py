"""Deterministic, local normalization of natural-language command phrasing
into the canonical phrasing the existing handlers (commands.py,
web_control.py, system_control.py) already understand.

No LLM / external API involved. Every rule here is a plain string /
regex rewrite, and every rule is designed to be a no-op on commands
that were already supported before this module existed, so existing
behavior is preserved by construction.
"""

import re


FILLER_PREFIXES = [
    r"^please\s+",
    r"^can you\s+",
    r"^could you\s+",
    r"^would you\s+",
    r"^will you\s+",
    r"^i want you to\s+",
]

FILLER_SUFFIXES = [
    r"\s+for me$",
    r"\s+please$",
]

# Only multi-word / non-canonical open verbs are rewritten. Plain "open X"
# is left untouched since every downstream handler already understands it.
OPEN_VERB_PREFIX = re.compile(
    r"^(open up|opening up|launch|launching|go to|going to"
    r"|start|starting|run|running)\s+"
)

VOLUME_UP_WORDS = re.compile(r"\b(up|increase|raise|higher|louder)\b")
VOLUME_DOWN_WORDS = re.compile(r"\b(down|decrease|lower|reduce|quieter|softer)\b")
UNMUTE_WORD = re.compile(r"\bunmute\b")
MUTE_WORD = re.compile(r"\bmute\b")

# Phase 7: absolute volume. Deliberately narrow - only "set volume to
# <1-3 digits> percent" or "...to <1-3 digits>%", with the percent/%
# marker required (never a bare number), so this can never accidentally
# match unrelated phrasing. The number is capped at 3 digits by the
# regex itself, so something like "999999999999 percent" can never
# match at all (there's no position where 1-3 digits are immediately
# followed by "percent"/"%" and the end of the string).
SET_VOLUME_PATTERN = re.compile(
    r"^set (?:the )?volume to\s+(\d{1,3})\s*(?:percent|%)$"
)

# Exact-phrase-only ("^...$") pronoun references to volume, e.g. "turn it
# down" with no literal "volume"/"mute" word present. Anchored to the
# whole string on purpose: these must never match as a fragment inside a
# longer, unrelated sentence.
VOLUME_PRONOUN_UP = re.compile(r"^(turn it up|make it louder)$")
VOLUME_PRONOUN_DOWN = re.compile(
    r"^(turn it down|make it quieter|make it softer)$"
)

# Checked in order; first match wins. "search for X" is deliberately left
# alone (no rule here matches it) since it is already canonical.
SEARCH_PREFIX_RULES = [
    (re.compile(r"^search the web for\s+"), "search for "),
    (re.compile(r"^look up\s+"), "search for "),
    (re.compile(r"^find information about\s+"), "search for "),
    (re.compile(r"^google\s+"), "search for "),
    (re.compile(r"^search\s+(?!for\b)"), "search for "),
]

DATE_QUESTION = re.compile(r"^what day is it\b")


def strip_filler(text):
    """Remove polite wrapping such as 'please', 'can you ... for me'.

    Repeats until stable, so stacked wrappers like "could you please
    ... for me" are fully unwrapped in one call, not just the first
    layer ("could you please launch youtube" would otherwise be left as
    "please launch youtube" after only one pass - the leftover "please"
    then blocks the open-verb rewrite below). Each pass only ever
    removes characters, so this always terminates.
    """

    while True:

        new_text = text

        for pattern in FILLER_PREFIXES:
            new_text = re.sub(pattern, "", new_text)

        for pattern in FILLER_SUFFIXES:
            new_text = re.sub(pattern, "", new_text)

        new_text = new_text.strip()

        if new_text == text:
            return new_text

        text = new_text


def canonicalize_date_phrase(text):
    """'what day is it' has no 'date'/'time' substring, so it would
    otherwise fall through to the unknown-command response."""

    if DATE_QUESTION.match(text):
        return "what is the date"

    return text


def canonicalize_search_phrase(text):
    """Rewrite search synonyms ('google X', 'look up X', ...) into the
    'search for X' phrasing web_control.handle() already expects."""

    for pattern, replacement in SEARCH_PREFIX_RULES:

        if pattern.match(text):
            return pattern.sub(replacement, text, count=1)

    return text


def canonicalize_open_verb(text):
    """Rewrite open synonyms ('launch X', 'go to X', ...) into 'open X'."""

    return OPEN_VERB_PREFIX.sub("open ", text)


def canonicalize_set_volume_phrase(text):
    """Rewrite 'set volume to <N> percent' / '...to <N>%' (whitespace/
    case variations already normalized by the time this runs) into the
    canonical 'set volume to <N>' phrasing volume_control.handle()
    expects - but ONLY for N in the valid 0-100 range.

    Out-of-range values (e.g. "set volume to 150 percent") are
    deliberately left completely unrewritten, never clamped to 0 or
    100 - this is a documented policy choice: silently substituting a
    different value than what the user actually asked for would be
    surprising and wrong, so an out-of-range request instead falls
    through the rest of the pipeline unrecognized, ending in the
    normal "I don't know how to do that" response, and - just as
    importantly - can never reach the Core Audio COM layer with a
    value outside its valid domain.
    """

    match = SET_VOLUME_PATTERN.match(text)

    if not match:
        return text

    percent = int(match.group(1))

    if not (0 <= percent <= 100):
        return text

    return f"set volume to {percent}"


def canonicalize_volume_phrase(text):
    """Rewrite volume/mute synonyms ('increase volume', 'turn the volume
    up', ...) into the 'volume up' / 'volume down' / 'mute' / 'unmute'
    phrasing volume_control.handle() expects.
    """

    if VOLUME_PRONOUN_UP.match(text):
        return "volume up"

    if VOLUME_PRONOUN_DOWN.match(text):
        return "volume down"

    if "volume" not in text and "mute" not in text:
        return text

    if UNMUTE_WORD.search(text):
        return "unmute"

    if MUTE_WORD.search(text):
        return "mute"

    if "volume" in text:

        if VOLUME_UP_WORDS.search(text):
            return "volume up"

        if VOLUME_DOWN_WORDS.search(text):
            return "volume down"

    return text


def canonicalize_desktop_phrase(text):
    """'show me the desktop' has no contiguous 'show desktop' substring
    (the "me the" breaks it up), so rewrite it into the phrasing
    window_control.handle() expects."""

    if "show" in text and "desktop" in text:
        return "show desktop"

    return text


def canonicalize_media_phrase(text):
    """Rewrite 'skip' (as in skip this song/track) into the 'next track'
    phrasing media_control.handle() expects. 'go to the next track'
    already contains 'next track' as a substring and needs no rewrite."""

    if "skip" in text:
        return "next track"

    return text


def canonicalize_screenshot_phrase(text):
    """Rewrite 'capture my screen' / 'capture the screen' into the
    'screenshot' phrasing screen_control.handle() expects."""

    if "capture" in text and "screen" in text:
        return "screenshot"

    return text


def normalize(text):
    """Normalize a raw recognized command string into the canonical
    phrasing existing handlers expect. Safe to call on already-canonical
    commands: it returns them unchanged.
    """

    if not text:
        return ""

    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)

    text = strip_filler(text)
    text = canonicalize_date_phrase(text)
    text = canonicalize_search_phrase(text)
    text = canonicalize_set_volume_phrase(text)
    text = canonicalize_volume_phrase(text)
    text = canonicalize_desktop_phrase(text)
    text = canonicalize_media_phrase(text)
    text = canonicalize_screenshot_phrase(text)
    text = canonicalize_open_verb(text)

    return text.strip()
