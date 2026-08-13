import re
import sys
import time

import commands
import config
import speech
import voice


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
