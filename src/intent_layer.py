"""Phase 10.2: rule-based intent fallback layer.

Additive-only. understand() is only ever consulted from commands.py
AFTER the entire existing deterministic pipeline (natural_language.
split_into_clauses() -> command_parser.normalize() -> the fixed
if/elif dispatch chain) has already failed to recognize a command -
see commands.py's insertion point, immediately before the final
"I don't know how to do that" fallback. This means:

- Every command that already works today is completely unaffected -
  zero added latency, zero behavior change, since this module is
  never even called for them.
- This module NEVER calls a control module (system_control,
  volume_control, web_control, window_control, media_control,
  keyboard_control, screen_control) directly. It only ever renders a
  recognized IntentFrame back into a canonical command string (the
  exact same strings the existing handlers already understand) and
  hands that string back to CommandProcessor.process() - the SAME
  method, called recursively, exactly like natural_language.
  split_into_clauses()'s existing clause loop already does. Because
  the Phase 9 dangerous-command confirmation gate is the unconditional
  first check at the top of process() on every call, including
  recursive ones, nothing this module produces can ever bypass it.

No LLM or external AI service, no new dependency - plain deterministic
string/regex matching, same style as command_parser.py and
intent_parser.py. This module does NOT modify intent_parser.py (which
is documented, tested, and diagnostics-only with a fixed IntentResult
shape) - it is a separate module that reuses intent_parser's fixed
allow-lists (KNOWN_APPLICATIONS, KNOWN_KEYS) by import, and adds two
intent categories intent_parser.py does not represent at all:
dangerous system commands (lock/shutdown/restart) and targeted-window
actions (see the Phase 10.2 architecture report, sections 4-5).

Known limitation, disclosed rather than hidden: because most existing
control-module handlers already match very broad bare substrings
(e.g. web_control.handle() treats "chrome" anywhere in the command as
"open Chrome"), a targeted-window or open-application phrase that
contains a known application name will usually already be "handled"
(sometimes with the wrong action - see TARGETED_WINDOW_ACTION below)
by an earlier dispatch step before this module is ever reached. This
module's TARGETED_WINDOW_ACTION and OPEN_APPLICATION rules are
included for completeness, direct unit testing, and defensive value
against any future dispatch reordering, but in practice they rescue
fewer real phrasings than the dangerous-command, volume-percentage,
search-query, and press-key rules below, which target real, verified
gaps in the existing dispatch chain (see the Phase 10.2 architecture
report and this module's tests for concrete before/after examples).
"""

import re

import config
import intent_parser
import natural_language


class Intent:
    # Existing categories, reused by name where the same canonical
    # command already exists in intent_parser.Intent.
    OPEN_APPLICATION = "OPEN_APPLICATION"
    SEARCH = "SEARCH"
    SET_VOLUME = "SET_VOLUME"
    PRESS_KEY = "PRESS_KEY"
    PLAY_PAUSE = "PLAY_PAUSE"
    TARGETED_WINDOW_ACTION = "TARGETED_WINDOW_ACTION"
    # New: intent_parser.py has zero representation of these - see the
    # Phase 10.2 architecture report, section 4.
    LOCK_COMPUTER = "LOCK_COMPUTER"
    SHUTDOWN_COMPUTER = "SHUTDOWN_COMPUTER"
    RESTART_COMPUTER = "RESTART_COMPUTER"


class IntentFrame:
    """A single recognized intent: intent + entities + confidence +
    the text it was derived from. See the Phase 10.2 architecture
    report, section 6, for the schema rationale."""

    __slots__ = ("intent", "entities", "confidence", "raw_text", "source", "incomplete")

    def __init__(
        self, intent, entities=None, confidence=0.0, raw_text="",
        source="rule_based", incomplete=False,
    ):
        self.intent = intent
        self.entities = entities or {}
        self.confidence = confidence
        self.raw_text = raw_text
        self.source = source
        # Phase 10.3: True for a frame that names a recognized intent
        # but is missing a required entity (currently only ever SEARCH
        # with no query - see SEARCH_INCOMPLETE_RE below). Default
        # False for every pre-existing frame shape, so nothing about
        # already-complete frames changes - to_canonical_command()
        # already independently returns None for any frame it can't
        # safely render (see its SEARCH branch), this field just lets
        # callers (commands.py's context layer, Phase 10.3) tell "ask a
        # follow-up question" apart from "genuinely unrecognized".
        self.incomplete = incomplete

    def __eq__(self, other):
        return (
            isinstance(other, IntentFrame)
            and self.intent == other.intent
            and self.entities == other.entities
            and self.confidence == other.confidence
            and self.incomplete == other.incomplete
        )

    def __repr__(self):
        return (
            f"IntentFrame({self.intent!r}, entities={self.entities!r}, "
            f"confidence={self.confidence!r}, incomplete={self.incomplete!r})"
        )


# Confidence values are a deliberate, documented design choice (see
# the Phase 10.2 architecture report, section 18), not derived from
# any statistical measurement - all comfortably clear the recommended
# default config.INTENT_CONFIDENCE_THRESHOLD (0.6).
CONFIDENCE_DANGEROUS = 0.8
CONFIDENCE_VOLUME = 0.75
CONFIDENCE_SEARCH = 0.75
CONFIDENCE_PRESS_KEY = 0.7
CONFIDENCE_TARGETED_WINDOW = 0.7
CONFIDENCE_PLAY_PAUSE = 0.7
CONFIDENCE_OPEN_APPLICATION = 0.8
# Phase 10.3: confidence for an INCOMPLETE SEARCH frame (see
# SEARCH_INCOMPLETE_RE below) - comfortably clears
# config.INTENT_CONFIDENCE_THRESHOLD (0.6), same deliberate-design-
# choice policy as every other confidence value in this module.
CONFIDENCE_SEARCH_INCOMPLETE = 0.7

# Bug-fix (Phase 10.2 validation): the original design checked the
# dangerous noun and the dangerous verb independently, anywhere in the
# text, with no relationship between them - so "computer shutdown
# information" (noun BEFORE verb, unrelated to a real command) and
# "shut down information about the computer" (verb far from the noun,
# with unrelated words in between) both incorrectly matched. These
# combined patterns instead require VERB, then (optionally) a single
# short article ("the"/"my"/"this"/"that"), then the NOUN, immediately
# adjacent - matching every legitimate example ("shut down the
# computer", "turn off the computer", "reboot the machine", "restart
# the pc", "lock the workstation") while rejecting reversed order and
# any phrase where unrelated words separate the verb from the noun.
_DANGEROUS_NOUN = r"(?:computer|pc|machine|system|workstation)"
_DANGEROUS_ARTICLE = r"(?:(?:the|my|this|that)\s+)?"

RESTART_DANGEROUS_RE = re.compile(
    rf"\b(?:restart|reboot)\b\s+{_DANGEROUS_ARTICLE}\b{_DANGEROUS_NOUN}\b"
)
SHUTDOWN_DANGEROUS_RE = re.compile(
    rf"\b(?:shut ?down|shut off|power off|turn off|switch off)\b"
    rf"\s+{_DANGEROUS_ARTICLE}\b{_DANGEROUS_NOUN}\b"
)
LOCK_DANGEROUS_RE = re.compile(
    rf"\block\b\s+{_DANGEROUS_ARTICLE}\b{_DANGEROUS_NOUN}\b"
)

# Bug-fix (Phase 10.2 validation): the original pattern
# (r"\b(\d{1,3})\s*(?:percent|%)") captured only a bare 1-3 digit run,
# so a negative sign or decimal point adjacent to the digits was
# simply ignored rather than rejected - "-10 percent" matched "10",
# and "40.5 percent" matched "5" (the fragment after the decimal
# point, since "\b" matches at the non-word "." boundary). This
# pattern instead captures the FULL numeric token, including any
# leading "-" and any decimal part, so the code below can explicitly
# reject anything that isn't a clean, unsigned, whole number - never
# silently reinterpreting a rejected value as a different one
# (reject-not-clamp, matching command_parser.canonicalize_set_volume_
# phrase()'s existing, documented policy).
VOLUME_NUMBER_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*(?:percent|%)")

SEARCH_FOR_RE = re.compile(r"search for (.+)$")

# Phase 10.3: "search <site>" with NOTHING after the site name names a
# site JARVIS can search WITHIN but supplies no query at all - e.g.
# "search youtube" means "search on YouTube [for ...]", not a Google
# search for the literal string "youtube". Deliberately scoped to
# exactly this one bare phrasing for exactly this one site (the only
# slot-fillable case this phase adds - see context_manager.py's module
# docstring) - not a general "any known site" rule. Checked in
# _understand_single() right after SEARCH_FOR_RE, so an actual query
# ("search youtube for cats" - out of scope for this phase, falls
# through to the existing generic SEARCH_PREFIX_RULES rewrite in
# command_parser.py exactly as before) is never mistaken for the bare,
# no-query case.
SEARCH_INCOMPLETE_SITES = ("youtube",)
SEARCH_INCOMPLETE_RE = re.compile(
    r"^search (?:" + "|".join(SEARCH_INCOMPLETE_SITES) + r")$"
)

KEY_WORD_PATTERNS = {
    key: re.compile(rf"\b{re.escape(key)}\b")
    for key in intent_parser.KNOWN_KEYS
}

# Bug-fix: browser tab-management phrases must never be swallowed by
# the bare "tab" PRESS_KEY rescue below - "tab" is a KNOWN_KEYS entry,
# so KEY_WORD_PATTERNS["tab"] previously matched ANY text containing
# "tab" as a standalone word, with no surrounding context required.
# That meant "open new tab" and the Roman-Urdu "tab band karo" were
# both mis-recognized as PRESS_KEY (-> "press tab"), instead of the
# browser tab actions they actually name (see web_control.py's
# new_tab()/close_tab()/next_tab()/previous_tab() and multilingual_
# normalizer._check_tab_browser()). A tab-management PHRASE (never
# bare "tab" alone) checked here wins over the single-word fallback -
# the same "narrow phrase overrides broad single-word rule" precedence
# this module already uses for TARGETED_ACTION_SYNONYMS_UR vs. the
# bare OPEN_APPLICATION fallback. Plain English phrasings ("new tab",
# "close tab") are matched by web_control.handle() directly, earlier
# in commands.py's dispatch chain, and never even reach this module -
# this list exists so the SAME plain-English phrases (which can also
# arrive here via jarvis.resolve_wake_word_omission(), a path that
# calls intent_layer.understand() directly without going through the
# primary dispatch chain first) and the Roman-Urdu/Urdu-script
# equivalents (which DO rely on reaching multilingual_normalizer,
# consulted only after this module) are never hijacked either way.
TAB_MANAGEMENT_MARKERS = (
    "new tab", "close tab", "next tab", "previous tab",
    "new chrome tab", "new browser tab", "new edge tab",
    "tab band karo", "tab band kar do",
    "naya tab kholo", "nya tab kholo", "new tab kholo",
)
TAB_MANAGEMENT_PATTERNS = [
    re.compile(r"\b" + re.escape(marker) + r"\b")
    for marker in TAB_MANAGEMENT_MARKERS
]

# Phase 11.12: "close the tab"/"close this tab"/"close the new tab" -
# the fixed-phrase list above only ever caught the exact, article-free
# "close tab", so these were falling through to the bare "tab" rescue
# just like "open new tab" originally did. Deliberately the SAME
# bounded article class (never an open "\bclose\b.*\btab\b") as web_
# control.CLOSE_TAB_RE - duplicated here rather than imported, because
# this module must stay pure and never import a control module (see
# this module's own docstring) even indirectly; the two patterns are
# kept in sync by hand, the same "defined once per side, deliberately
# not shared" discipline commands.DANGEROUS_COMMANDS already uses for
# system_control.py's dangerous phrases.
_TAB_MANAGEMENT_CLOSE_RE = re.compile(
    r"\bclose\b\s+(?:(?:the|this|a|new)\s+)*tab\b"
)


def _is_tab_management_phrase(text):
    if _TAB_MANAGEMENT_CLOSE_RE.search(text):
        return True
    return any(pattern.search(text) for pattern in TAB_MANAGEMENT_PATTERNS)

# Action-word synonyms not already covered by window_control.handle_
# targeted()'s own fixed word set (minimize/maximize/restore/close/
# switch - see the Phase 10.2 architecture report, section 5).
TARGETED_ACTION_SYNONYMS = {
    "kill": "close",
    "hide": "minimize",
    "bring back": "restore",
    "switch to": "switch",
}

# Phase 11.7: Roman-Urdu/Urdu-script "close" synonyms - e.g. "youtube
# band karo" ("close youtube"). Without this, a phrase like "youtube
# band karo" would fall all the way through to the OPEN_APPLICATION
# catch-all below (a known app name is present, no ENGLISH synonym
# above matches "band karo") and incorrectly OPEN YouTube instead of
# closing it - exactly the class of bug this module's TARGETED_WINDOW_
# ACTION rule exists to prevent for the English synonyms above.
# Deliberately its own, PHRASE-level (never bare "karo"/"کرو") dict,
# checked via a word-boundary-anchored regex (see TARGETED_ACTION_
# SYNONYMS_UR_RE below) rather than folded into the bare `in text`
# substring loop above, which existing English synonyms use: a bare
# substring check would let "youtube band karobar" ("business", a real
# Urdu/Roman-Urdu word sharing a prefix with "karo") false-match "band
# karo" and incorrectly close YouTube - the exact false-positive class
# multilingual_normalizer._contains_any_bounded() already guards
# against for the same vocabulary; this closes the same gap here.
TARGETED_ACTION_SYNONYMS_UR = {
    "band karo": "close",
    "band kar do": "close",
    "close karo": "close",
    "close kar do": "close",
    "بند کرو": "close",
    "بند کر دو": "close",
}
TARGETED_ACTION_SYNONYMS_UR_RE = {
    synonym: re.compile(r"\b" + re.escape(synonym) + r"\b")
    for synonym in TARGETED_ACTION_SYNONYMS_UR
}


def _find_known_application(text):
    for name in intent_parser.KNOWN_APPLICATIONS:
        if name in text:
            return name
    return None


def _understand_single(text):
    """Try every rule against `text` as a single, whole utterance.
    Returns one IntentFrame, or None if nothing matched. Operates on
    already-normalized text - same contract as intent_parser.
    classify()."""

    if not text:
        return None

    # DANGEROUS (checked first, deliberately - see module docstring
    # and the Phase 10.2 architecture report, section 14). Verb and
    # noun must be adjacent (see RESTART_DANGEROUS_RE et al. above) -
    # a bare noun/verb appearing anywhere is no longer sufficient.
    if RESTART_DANGEROUS_RE.search(text):
        return IntentFrame(
            Intent.RESTART_COMPUTER,
            confidence=CONFIDENCE_DANGEROUS,
            raw_text=text,
        )

    if SHUTDOWN_DANGEROUS_RE.search(text):
        return IntentFrame(
            Intent.SHUTDOWN_COMPUTER,
            confidence=CONFIDENCE_DANGEROUS,
            raw_text=text,
        )

    if LOCK_DANGEROUS_RE.search(text):
        return IntentFrame(
            Intent.LOCK_COMPUTER,
            confidence=CONFIDENCE_DANGEROUS,
            raw_text=text,
        )

    # SET_VOLUME - rescues phrasings command_parser.SET_VOLUME_PATTERN
    # doesn't cover because they're missing its required verb ("set/
    # make/turn/change") or place the number before the word "volume".
    if "volume" in text:

        number_match = VOLUME_NUMBER_RE.search(text)

        if number_match:

            raw_number = number_match.group(1)

            # Reject-not-clamp: a negative sign or a decimal point
            # anywhere in the matched token means this was NOT a
            # clean whole number in the first place - str.isdigit()
            # is False for both "-10" and "40.5", so neither is ever
            # misread as a different, smaller positive integer.
            if raw_number.isdigit():

                percent = int(raw_number)

                if 0 <= percent <= 100:
                    return IntentFrame(
                        Intent.SET_VOLUME,
                        entities={"percent": percent},
                        confidence=CONFIDENCE_VOLUME,
                        raw_text=text,
                    )

    # SEARCH - rescues "search for X" appearing mid-sentence (e.g. "i
    # want to search for X"), not just at the very start of the
    # command, which is all command_parser.py's anchored rules cover.
    search_match = SEARCH_FOR_RE.search(text)

    if search_match:

        query = search_match.group(1).strip()

        if query:
            return IntentFrame(
                Intent.SEARCH,
                entities={"query": query},
                confidence=CONFIDENCE_SEARCH,
                raw_text=text,
            )

    # SEARCH (incomplete) - Phase 10.3: "search youtube" names a site
    # to search within but supplies no query - marked incomplete
    # rather than falling through to OPEN_APPLICATION below, so
    # commands.py's context layer (Phase 10.3, only consulted when
    # config.ENABLE_CONTEXT_LAYER is True) can ask a follow-up
    # question instead of silently opening the site. Checked before
    # the OPEN_APPLICATION fallback so it wins for this one specific
    # bare phrasing; every other phrasing that names "youtube" (e.g.
    # "open youtube", "launch youtube") is completely unaffected and
    # still resolves to OPEN_APPLICATION exactly as before this phase.
    if SEARCH_INCOMPLETE_RE.match(text):
        return IntentFrame(
            Intent.SEARCH,
            entities={},
            confidence=CONFIDENCE_SEARCH_INCOMPLETE,
            raw_text=text,
            incomplete=True,
        )

    # PRESS_KEY - rescues "hit enter"/"tab key" style phrasings that
    # don't contain the literal "press <key>" substring. "tab" is
    # skipped when a browser tab-management phrase is present (see
    # TAB_MANAGEMENT_MARKERS above) - it names a browser tab, not the
    # Tab key, in that context.
    for key, pattern in KEY_WORD_PATTERNS.items():

        if key == "tab" and _is_tab_management_phrase(text):
            continue

        if pattern.search(text):
            return IntentFrame(
                Intent.PRESS_KEY,
                entities={"key": key},
                confidence=CONFIDENCE_PRESS_KEY,
                raw_text=text,
            )

    app_name = _find_known_application(text)

    # TARGETED_WINDOW_ACTION - checked before bare OPEN_APPLICATION so
    # a more specific "kill chrome"-style phrase wins over treating it
    # as merely opening the application. See the module docstring's
    # "known limitation" note: in practice, most real dispatch calls
    # never reach this rule because an earlier handler's bare
    # substring match already intercepts app-name-containing phrases.
    if app_name is not None:

        for synonym, action in TARGETED_ACTION_SYNONYMS.items():

            if synonym in text:
                return IntentFrame(
                    Intent.TARGETED_WINDOW_ACTION,
                    entities={"application": app_name, "action": action},
                    confidence=CONFIDENCE_TARGETED_WINDOW,
                    raw_text=text,
                )

        # Phase 11.7: Roman-Urdu/Urdu-script "close" synonyms - see
        # TARGETED_ACTION_SYNONYMS_UR's own comment above for why this
        # is a separate, word-boundary-anchored check rather than
        # folded into the bare-substring loop above.
        for synonym, action in TARGETED_ACTION_SYNONYMS_UR.items():

            if TARGETED_ACTION_SYNONYMS_UR_RE[synonym].search(text):
                return IntentFrame(
                    Intent.TARGETED_WINDOW_ACTION,
                    entities={"application": app_name, "action": action},
                    confidence=CONFIDENCE_TARGETED_WINDOW,
                    raw_text=text,
                )

    # PLAY_PAUSE - "resume" has no substring overlap with media_
    # control.handle()'s "play"/"pause" checks.
    if "resume" in text:
        return IntentFrame(
            Intent.PLAY_PAUSE,
            confidence=CONFIDENCE_PLAY_PAUSE,
            raw_text=text,
        )

    # OPEN_APPLICATION - last resort; see module docstring's "known
    # limitation" note, same caveat as TARGETED_WINDOW_ACTION above.
    if app_name is not None:
        return IntentFrame(
            Intent.OPEN_APPLICATION,
            entities={"application": app_name},
            confidence=CONFIDENCE_OPEN_APPLICATION,
            raw_text=text,
        )

    return None


def understand(text):
    """Return a list of IntentFrame - zero, one, or (for a bounded,
    all-or-nothing "and"/"then" split, deliberately mirroring
    natural_language.split_into_clauses()'s own all-or-nothing policy)
    more than one. Never raises. Operates on already-normalized text -
    same contract as intent_parser.classify().

    Splitting on "and"/"then" (reusing natural_language.py's own
    conjunction pattern by reference, not duplicating it) is tried
    FIRST, and only committed to if EVERY resulting clause
    independently produces a confident frame - exactly the same
    fail-closed philosophy split_into_clauses() uses. If the split
    isn't applicable (fewer than 2 candidates) or isn't fully
    resolved, `text` is tried as a single whole unit instead - this
    order matters: trying the split first is what lets "power off the
    computer and hit enter" resolve to two separate frames instead of
    the whole-string dangerous-command rule matching first and
    silently absorbing the "hit enter" half. The single-unit fallback
    is still needed for phrases like "search for bed and breakfast"
    (a real, pre-existing example from natural_language.py's own
    docstring): splitting produces ["search for bed", "breakfast"],
    "breakfast" alone matches no rule, so the split is rejected and
    the whole string is tried instead - SEARCH_FOR_RE's greedy match
    then correctly captures "bed and breakfast" as one query, exactly
    matching this project's existing documented behavior for that
    phrase.
    """

    if not text:
        return []

    candidates = [
        clause.strip()
        for clause in natural_language.CONJUNCTION_PATTERN.split(text)
        if clause.strip()
    ]

    if len(candidates) >= 2:

        frames = []
        split_ok = True

        for clause in candidates:

            clause_frame = _understand_single(clause)

            if (
                clause_frame is None
                or clause_frame.confidence < config.INTENT_CONFIDENCE_THRESHOLD
            ):
                split_ok = False
                break

            frames.append(clause_frame)

        if split_ok:
            return frames

    frame = _understand_single(text)

    if frame is not None:
        return [frame]

    return []


def to_canonical_command(frame):
    """Render an IntentFrame back into the canonical command string
    the existing handler modules already understand. Returns None if
    the frame can't be safely rendered (e.g. an out-of-allow-list
    entity) - callers must treat None as "nothing to do", never guess.

    Can only ever produce one of a fixed set of literal strings (or a
    'search for <query>'/'set volume to <N>' string built from an
    already-validated entity) - it cannot construct an arbitrary
    command, exactly like intent_parser.to_canonical_command().
    """

    intent = frame.intent
    entities = frame.entities

    if intent == Intent.RESTART_COMPUTER:
        return "restart computer"

    if intent == Intent.SHUTDOWN_COMPUTER:
        return "shutdown computer"

    if intent == Intent.LOCK_COMPUTER:
        return "lock computer"

    if intent == Intent.SET_VOLUME:

        percent = entities.get("percent")

        if isinstance(percent, int) and not isinstance(percent, bool) and 0 <= percent <= 100:
            return f"set volume to {percent}"

        return None

    if intent == Intent.SEARCH:

        query = entities.get("query")

        if query:
            return f"search for {query}"

        return None

    if intent == Intent.PRESS_KEY:

        key = entities.get("key")

        if key in intent_parser.KNOWN_KEYS:
            return f"press {key}"

        return None

    if intent == Intent.PLAY_PAUSE:
        return "play"

    if intent == Intent.TARGETED_WINDOW_ACTION:

        app = entities.get("application")
        action = entities.get("action")

        if (
            app in intent_parser.KNOWN_APPLICATIONS
            and action in ("minimize", "maximize", "restore", "close", "switch")
        ):
            return f"{action} {app}"

        return None

    if intent == Intent.OPEN_APPLICATION:

        app = entities.get("application")

        return intent_parser.KNOWN_APPLICATIONS.get(app)

    return None
