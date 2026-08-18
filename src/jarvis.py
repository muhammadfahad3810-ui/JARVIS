import re
import sys
import time

import command_parser
import commands
import config
import intent_layer
import multilingual_normalizer
import speech
import voice


# =============================================================
# PHASE 11.9: console I/O hardening (Step 2)
# =============================================================
#
# Confirmed live bug (Phase 11.8 validation session): on this Windows
# machine's default console codec (cp1252), a bare print() of arbitrary
# STT transcription text - e.g. Whisper hallucinating non-Latin-1 text
# from ambient noise/silence, or a genuine Urdu-script recognition
# result - raises an uncaught UnicodeEncodeError. That exception
# propagates all the way up through main()'s own except Exception
# handler and terminates the ENTIRE process (sys.exit(1)), losing the
# whole running session over what is purely a CONSOLE DISPLAY problem,
# never a problem with the recognized text itself.
#
# Fix: reconfigure sys.stdout/sys.stderr to UTF-8 with errors="replace"
# ONCE, at process startup, before any listening begins. This changes
# nothing about what text is captured, recognized, normalized, or
# executed anywhere in the pipeline - only how already-failing encode
# operations at the console boundary degrade (substituting the
# U+FFFD replacement character for anything even UTF-8 somehow
# couldn't represent - which is effectively never, since UTF-8 can
# encode any Python str) instead of raising and killing the process.
# This is the smallest possible fix: one call, one place, zero changes
# to any command/text value used internally. See test_wake_word.py's
# Phase 11.9 section for regression coverage, including a real
# io.TextIOWrapper proving a previously-crashing print() now succeeds.
def harden_console_io(stdout=None, stderr=None):
    """Reconfigure `stdout`/`stderr` (defaulting to sys.stdout/sys.
    stderr) to UTF-8 with errors="replace", if they support it. Never
    raises - some stream types (certain test harnesses, redirected
    output, IDE consoles) don't expose reconfigure() at all, or reject
    the arguments; either case is silently skipped, exactly as if this
    function had never been called, rather than blocking startup."""

    for stream in (stdout or sys.stdout, stderr or sys.stderr):

        reconfigure = getattr(stream, "reconfigure", None)

        if reconfigure is None:
            continue

        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def _build_wake_word_pattern(aliases):
    escaped = "|".join(re.escape(alias) for alias in aliases)
    return re.compile(rf"\b(?:{escaped})(?:'s)?\b")


# Matches the wake word or a known alias ("jervis"), optionally followed
# by a possessive "'s" ("jarvis's"), as a whole word only - so accidental
# words that merely contain "jarvis" as a substring (e.g. "jarvison")
# are correctly NOT treated as the wake word.
WAKE_WORD_PATTERN = _build_wake_word_pattern(config.WAKE_WORD_ALIASES)


def contains_wake_word(text, pattern=None):
    """True if text contains the wake word (or a known alias) as a whole
    word."""

    pattern = pattern or WAKE_WORD_PATTERN

    return pattern.search(text) is not None


def extract_command_after_wake_word(text, pattern=None):
    """Strip the wake word from a recognized phrase.

    Returns:
        None if the wake word is not present at all.
        "" if the wake word was said with nothing after it.
        The remaining text otherwise.

    Handles:
      - alternate wake-word phrasing ("jervis", "jarvis's")
      - accidental repeats from the speech recognizer, e.g.
        "jarvis jarvis open chrome" -> "open chrome", instead of
        treating the leftover "jarvis" as part of an unknown command.
      - words that merely contain "jarvis" as a substring (e.g.
        "jarvison") are correctly NOT treated as the wake word.
    """

    pattern = pattern or WAKE_WORD_PATTERN

    match = pattern.search(text)

    if match is None:
        return None

    remaining = text[match.end():].strip()

    while True:

        repeat = pattern.match(remaining)

        if repeat is None:
            break

        remaining = remaining[repeat.end():].strip()

    return remaining


# =============================================================
# PHASE 11.9: wake-word-omission recovery (Step 3)
# =============================================================

def resolve_wake_word_omission(text):
    """Pure - never executes anything, never calls a control module,
    never calls voice/speech I/O. Returns a canonical command string,
    or None. `text` is a FULL heard utterance in which the wake word
    was NOT found (see extract_command_after_wake_word() returning
    None for it).

    Reuses the SAME two pure fallback resolvers commands.
    CommandProcessor.process() itself already uses - intent_layer.py
    and multilingual_normalizer.py - rather than a new/parallel
    classifier, so "would this resolve to a known command" is answered
    identically to how process() would answer it, had the wake word
    only been present. Deliberately conservative: only a SINGLE,
    confident, COMPLETE frame from intent_layer.understand() is
    accepted (a multi-clause result, or an incomplete slot-fillable
    one, is too ambiguous for an unattended spoken confirmation prompt
    and is treated as "no resolution" instead of guessing).

    Structurally, not just by policy, never returns one of commands.
    DANGEROUS_COMMANDS - callers (see Jarvis._maybe_recover_omitted_
    wake_word()) must never offer a "did you mean" confirmation for a
    dangerous command without the wake word, and this function already
    refuses to produce one, as defense in depth on top of the existing
    Phase 9 gate that still applies at actual execution time.
    """

    if not text:
        return None

    normalized = command_parser.normalize(text)

    if not normalized:
        return None

    canonical = None

    if config.ENABLE_INTENT_FALLBACK_LAYER:

        frames = intent_layer.understand(normalized)

        confident_frames = [
            frame for frame in frames
            if frame.confidence >= config.INTENT_CONFIDENCE_THRESHOLD
        ]

        if len(confident_frames) == 1 and not confident_frames[0].incomplete:
            canonical = intent_layer.to_canonical_command(confident_frames[0])

    if canonical is None and config.ENABLE_MULTILINGUAL_LAYER:
        canonical = multilingual_normalizer.understand(normalized)

    if canonical is None:
        return None

    if canonical in commands.DANGEROUS_COMMANDS:
        return None

    return canonical


# Phase 11.11 (Step 7): a DELIBERATELY SEPARATE, wider affirmative-word
# list from commands.CONFIRM_WORDS - used ONLY by Jarvis._maybe_
# recover_omitted_wake_word() below to confirm a NON-dangerous command
# resolve_wake_word_omission() already resolved (see that function's
# own docstring: it structurally can never return one of commands.
# DANGEROUS_COMMANDS). commands.CONFIRM_WORDS/is_confirm_command()
# guard the Phase 9 dangerous-command confirmation gate and are
# DELIBERATELY left untouched by this phase - test_security.py's
# test_confirmation_gate_only_accepts_the_fixed_allow_list already
# documents, as a deliberate Phase 9 security decision, that casual
# affirmatives like "yeah" must NEVER confirm a dangerous command;
# widening that shared list would have silently broken that guarantee.
# Since this list can only ever gate a command already proven safe (not
# a lock/shutdown/restart), a wider, more forgiving set of affirmatives
# is an appropriate, low-risk usability improvement here specifically -
# still deliberately conservative (single, distinct affirmative TOKENS
# only, word-boundary matched, never a phrase fragment), matching the
# same "narrow explicit marker" discipline used throughout this
# project's multilingual vocabulary.
WAKE_WORD_RECOVERY_CONFIRM_WORDS = (
    "yes", "yeah", "confirm", "confirmed", "haan", "han",
    "جی ہاں", "جی",
)
WAKE_WORD_RECOVERY_CONFIRM_PATTERN = _build_wake_word_pattern(
    WAKE_WORD_RECOVERY_CONFIRM_WORDS
)


def is_wake_word_recovery_confirmation(text):
    """Pure. True if `text` contains one of WAKE_WORD_RECOVERY_CONFIRM_
    WORDS as a whole word/phrase - reusing _build_wake_word_pattern()'s
    own word-boundary alternation-building logic (already tested,
    already handles Urdu-script text correctly) rather than duplicating
    it. Anything that doesn't match - including "no"/"nahi"/"نہیں",
    silence, or an unrelated reply - fails closed: Jarvis._maybe_
    recover_omitted_wake_word() only executes on an explicit True from
    this function, never on the absence of a recognized decline."""

    if not text:
        return False

    return WAKE_WORD_RECOVERY_CONFIRM_PATTERN.search(text) is not None


class Jarvis:

    def __init__(self):

        self.voice = voice.Voice()
        self.speech = speech.Speech(self.voice)
        self.commands = commands.CommandProcessor(self.voice)

        self.running = True

        self.speech.calibrate_microphone()

    # =========================================================
    # COMMAND DISPATCH
    # =========================================================

    def process_command(self, command):

        if not self.commands.process(command):
            self.running = False

    # =========================================================
    # WAKE WORD
    # =========================================================

    def wait_for_wake_word(self):

        heard = self.speech.listen(
            timeout=config.WAKE_LISTEN_TIMEOUT,
            phrase_limit=config.WAKE_PHRASE_LIMIT
        )

        if not heard:
            return

        remaining = extract_command_after_wake_word(heard)

        if config.DEBUG:
            print(
                f"[DEBUG] heard='{heard}' "
                f"wake_word_detected={remaining is not None} "
                f"extracted='{remaining}'"
            )

        if remaining is None:
            self._maybe_recover_omitted_wake_word(heard)
            return

        # Example:
        # Jarvis open YouTube

        if remaining:

            self.process_command(remaining)

        # Example:
        # Jarvis

        else:

            self.voice.speak("Yes?")

            heard = self.speech.listen_with_retry(
                timeout=config.COMMAND_LISTEN_TIMEOUT,
                phrase_limit=config.COMMAND_PHRASE_LIMIT
            )

            if heard:

                self.process_command(heard)

    def _maybe_recover_omitted_wake_word(self, heard):
        """Phase 11.9 (Step 3). Called only when `heard` did NOT contain
        the wake word at all. Off by default (config.ENABLE_WAKE_WORD_
        OMISSION_TOLERANCE) - with the flag False (the default), this
        is a no-op and behavior is byte-for-byte unchanged from before
        this phase.

        Never executes `heard` (or anything derived from it) directly:
        resolve_wake_word_omission() is pure and only ever returns a
        canonical command string (never a dangerous one - see its own
        docstring) or None. A resolved command is only ever executed
        after an explicit spoken "yes" reply, through self.
        process_command() - the exact same path, and therefore the
        exact same Phase 9 dangerous-command gate and every other
        existing safety check, that every other command in this
        project already goes through. The confirmation reply itself
        does not need to repeat the wake word, mirroring commands.
        CommandProcessor's own existing dangerous-command confirmation
        flow (self._pending_confirmation), which has never required it
        either.

        Phase 11.11 (Step 7): the confirmation reply is checked with
        is_wake_word_recovery_confirmation() - a wider, but still
        conservative, affirmative-word list than commands.
        is_confirm_command() (which stays reserved for the Phase 9
        dangerous-command gate - see WAKE_WORD_RECOVERY_CONFIRM_WORDS'
        own comment for why sharing that list would have been unsafe).
        Safe to widen here specifically because `canonical` can
        structurally never be a dangerous command (see resolve_wake_
        word_omission()'s own docstring) - the worst case of a
        misheard "no" being taken as "yes" here is a wrong NON-
        dangerous action, not a security bypass.
        """

        if not config.ENABLE_WAKE_WORD_OMISSION_TOLERANCE:
            return

        canonical = resolve_wake_word_omission(heard)

        if canonical is None:
            return

        self.voice.speak(
            f"Did you mean: {canonical}? Say yes to confirm."
        )

        reply = self.speech.listen_with_retry(
            timeout=config.COMMAND_LISTEN_TIMEOUT,
            phrase_limit=config.COMMAND_PHRASE_LIMIT
        )

        if reply and is_wake_word_recovery_confirmation(reply):
            self.process_command(canonical)
        else:
            self.voice.speak("Okay, never mind.")

    # =========================================================
    # MAIN LOOP
    # =========================================================

    def run(self):

        self.voice.speak(
            "JARVIS online. "
            "Say my name when you need me."
        )

        while self.running:

            try:

                self.wait_for_wake_word()

                time.sleep(0.2)

            except KeyboardInterrupt:

                print("\nJARVIS stopped.")

                break

        print("JARVIS offline.")


# =============================================================
# PROGRAM ENTRY
# =============================================================

def main():

    harden_console_io()

    try:

        jarvis = Jarvis()

        jarvis.run()

    except KeyboardInterrupt:

        print("\nJARVIS stopped.")

    except Exception as error:

        print(
            f"\nJARVIS ERROR: {error}"
        )

        sys.exit(1)


if __name__ == "__main__":

    main()
