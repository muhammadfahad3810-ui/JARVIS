import datetime
import re

import command_parser
import config
import intent_parser
import keyboard_control
import media_control
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

    def process(self, command):
        """Process a single command.

        Returns False if this was an exit command (caller should stop
        the main loop), True otherwise.
        """

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
