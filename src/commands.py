import datetime
import re

import command_parser
import config
import intent_parser
import keyboard_control
import media_control
import natural_language
import screen_control
import system_control
import volume_control
import web_control
import window_control


GREETINGS = [
    "hello",
    "hi",
    "hey",
    "good morning",
    "good afternoon",
    "good evening",
]

EXIT_WORDS = [
    "exit",
    "quit",
    "goodbye",
    "go offline",
]


def _word_boundary_patterns(words):
    """Compile each phrase as a whole-word/whole-phrase regex, so short
    words like 'hi' don't false-match inside unrelated words like
    'this' (a bare `"hi" in command` substring check would)."""

    return [
        re.compile(r"\b" + re.escape(word) + r"\b")
        for word in words
    ]


GREETING_PATTERNS = _word_boundary_patterns(GREETINGS)
EXIT_PATTERNS = _word_boundary_patterns(EXIT_WORDS)

# Phase 9: confirmation layer for dangerous system commands. These are
# the exact same three fixed phrases system_control.handle_system()
# matches - defined once here (not imported from system_control.py) so
# system_control.py needs zero changes and stays fully protected.
DANGEROUS_COMMANDS = ("lock computer", "shutdown computer", "restart computer")

DANGEROUS_COMMAND_PROMPTS = {
    "lock computer": "Are you sure you want to lock the computer? Say yes to confirm.",
    "shutdown computer": "Are you sure you want to shut down the computer? Say yes to confirm.",
    "restart computer": "Are you sure you want to restart the computer? Say yes to confirm.",
}

CONFIRM_WORDS = ["yes", "confirm", "confirmed"]
CONFIRM_PATTERNS = _word_boundary_patterns(CONFIRM_WORDS)


def is_confirm_command(command):
    return any(pattern.search(command) for pattern in CONFIRM_PATTERNS)


def _light_normalize(text):
    """Lowercase + whitespace-collapse ONLY - deliberately NOT the full
    command_parser.normalize() pipeline. normalize() can rewrite (and
    thereby destroy) a dangerous phrase before this gate ever sees it:
    e.g. "restart computer and mute" -> normalize() -> "mute" (via
    canonicalize_volume_phrase(), which rewrites the ENTIRE string to
    just "mute" whenever the word "mute" appears anywhere in it - a
    pre-existing Phase 5 behavior, unrelated to and not modified by
    Phase 9). Checking dangerous phrases on this lightly-normalized
    text instead - before normalize() ever runs - means the phrase is
    always seen intact, regardless of what normalize() would later do
    to the rest of the string."""

    return re.sub(r"\s+", " ", (text or "").lower().strip())


def _matched_dangerous_command(command):
    """Return the first DANGEROUS_COMMANDS phrase found as a substring
    of `command`, or None - mirrors system_control.handle_system()'s
    own bare-substring matching exactly, so a phrase like "lock
    computer and open chrome" (which handle_system() would still act
    on, discarding the suffix - see test_security.py's Phase 6
    "dangerous suffix" tests) is caught by the confirmation gate too,
    not just an exact "lock computer" match."""

    for phrase in DANGEROUS_COMMANDS:
        if phrase in command:
            return phrase

    return None


def handle_information(command, voice):

    if "time" in command:

        current_time = datetime.datetime.now().strftime(
            "%I:%M %p"
        )

        voice.speak(
            f"The current time is {current_time}."
        )

        return True

    if "date" in command:

        current_date = datetime.datetime.now().strftime(
            "%A, %B %d, %Y"
        )

        voice.speak(
            f"Today is {current_date}."
        )

        return True

    return False


def handle_greeting(command, voice):

    if any(pattern.search(command) for pattern in GREETING_PATTERNS):

        voice.speak(
            "Hello. I am JARVIS. "
            "How can I help you?"
        )

        return True

    return False


def is_exit_command(command):
    return any(pattern.search(command) for pattern in EXIT_PATTERNS)


class CommandProcessor:
    """Routes a recognized command string to the right handler."""

    def __init__(self, voice):
        self.voice = voice
        # Phase 9: set to a pending dangerous-command string between the
        # confirmation prompt and the reply that resolves it. None the
        # rest of the time (the overwhelming majority of this object's
        # lifetime) - see DANGEROUS_COMMANDS/is_confirm_command() above.
        self._pending_confirmation = None

    def process(self, command):
        """Process a single command.

        Returns False if this was an exit command (caller should stop
        the main loop), True otherwise.

        Phase 8: if `command` deterministically splits into more than
        one already-known clause (see natural_language.split_into_
        clauses() - "open chrome and search for python"), each clause
        is processed independently, in order, through this exact same
        method - no validation is bypassed, nothing here executes a
        clause directly. If it does NOT cleanly split (including the
        common case of a single, unchanged command), `command` is used
        completely unmodified below, byte-for-byte identical to before
        Phase 8.

        Phase 9: if a dangerous command is awaiting confirmation (see
        DANGEROUS_COMMANDS above), THIS call is treated purely as the
        yes/no reply to it - resolved first, before wake-word-stripped
        text is split, normalized, or dispatched in any way. Only
        reachable at all when config.REQUIRE_CONFIRMATION_FOR_DANGEROUS_
        COMMANDS is True; when it's False (the default), self.
        _pending_confirmation can never become non-None, so this branch
        is dead code and behavior is byte-for-byte unchanged from before
        Phase 9.
        """

        if self._pending_confirmation is not None:

            pending = self._pending_confirmation
            self._pending_confirmation = None

            if is_confirm_command(_light_normalize(command)):
                return system_control.handle_system(pending, self.voice)

            self.voice.speak("Cancelled.")
            return True

        # DANGEROUS COMMAND CONFIRMATION GATE (Phase 9) - checked here,
        # first, on lightly-normalized RAW text - deliberately BEFORE
        # natural_language.split_into_clauses() and BEFORE command_
        # parser.normalize(). Two independent reasons this ordering is
        # load-bearing, not stylistic:
        #
        # 1. A phrase like "lock computer and open chrome" is never
        #    split by split_into_clauses() (intent_parser.classify(
        #    "lock computer") is UNKNOWN - there is no SYSTEM category
        #    in that classifier - so the all-or-nothing split safety
        #    correctly refuses to split it), so the WHOLE unsplit
        #    phrase reaches this dispatch chain as one string. If this
        #    gate ran any later than the earliest possible point, an
        #    earlier-checked branch (e.g. web_control.handle()'s bare
        #    "chrome" substring match) would fire first and execute
        #    before the dangerous phrase was ever evaluated.
        #
        # 2. command_parser.normalize() itself can DESTROY a dangerous
        #    phrase before this gate would ever see it if checked after
        #    normalize() ran: "restart computer and mute" normalizes to
        #    just "mute" (canonicalize_volume_phrase() rewrites the
        #    ENTIRE string to "mute" whenever that word appears
        #    anywhere in it - pre-existing since Phase 5, not modified
        #    here). Checking the lightly-normalized (lowercase/
        #    whitespace-collapsed only, NOT the full normalize()
        #    pipeline) raw text instead means the dangerous phrase is
        #    always seen intact.
        #
        # Default False -> this whole block never executes, so behavior
        # is byte-for-byte unchanged from before Phase 9.
        if config.REQUIRE_CONFIRMATION_FOR_DANGEROUS_COMMANDS:

            light_command = _light_normalize(command)
            matched = _matched_dangerous_command(light_command)

            if matched:
                self._pending_confirmation = light_command
                self.voice.speak(DANGEROUS_COMMAND_PROMPTS[matched])
                return True

        clauses = natural_language.split_into_clauses(command)

        if len(clauses) > 1:

            if config.DEBUG:
                print(f"[DEBUG] split '{command}' into clauses: {clauses}")

            result = True

            for clause in clauses:
                if not self.process(clause):
                    result = False

            return result

        raw_command = command
        command = command_parser.normalize(command)

        if config.DEBUG:
            print(f"[DEBUG] raw='{raw_command}' normalized='{command}'")

            intent_result = intent_parser.classify(command)
            print(
                f"[DEBUG] intent={intent_result.intent} "
                f"target={intent_result.target!r}"
            )

        if not command:
            return True

        # EXIT
        if is_exit_command(command):

            self.voice.speak(
                "Going offline. Goodbye."
            )

            return False

        # INFORMATION
        if handle_information(command, self.voice):
            return True

        # GREETING
        if handle_greeting(command, self.voice):
            return True

        # TARGETED WINDOW CONTROL (Phase 6) - must run before WEB, since
        # e.g. "close chrome" would otherwise be caught by web_control's
        # bare "chrome" substring check, which only knows how to OPEN
        # Chrome, not close a specific window. Only intercepts commands
        # that name a known application from the fixed allow-list; any
        # other command (including all untargeted window commands) is
        # unaffected and falls through to the unchanged chain below.
        if window_control.handle_targeted(command, self.voice):
            return True

        # WEB
        if web_control.handle(command, self.voice):
            return True

        # APPLICATIONS
        if system_control.handle_application(command, self.voice):
            return True

        # SYSTEM
        if system_control.handle_system(command, self.voice):
            return True

        # WINDOW CONTROL
        if window_control.handle(command, self.voice):
            return True

        # VOLUME
        if volume_control.handle(command, self.voice):
            return True

        # MEDIA
        if media_control.handle(command, self.voice):
            return True

        # SCREEN
        if screen_control.handle(command, self.voice):
            return True

        # KEYBOARD
        if keyboard_control.handle(command, self.voice):
            return True

        # UNKNOWN
        self.voice.speak(
            "I heard you, but I don't "
            "know how to do that yet."
        )

        return True
