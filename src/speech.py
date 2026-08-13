import time

import speech_recognition as sr

import config


class Speech:
    """Handles microphone input and speech-to-text recognition."""

    def __init__(self, voice):

        self.voice = voice

        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = config.ENERGY_THRESHOLD
        self.recognizer.dynamic_energy_threshold = config.DYNAMIC_ENERGY_THRESHOLD
        self.recognizer.pause_threshold = config.PAUSE_THRESHOLD
        self.recognizer.non_speaking_duration = config.NON_SPEAKING_DURATION

        self._last_request_error_announcement = None

    def calibrate_microphone(self):
        """One-time ambient noise calibration, meant to be called once at
        startup. Sets a better starting energy_threshold based on actual
        room noise; dynamic_energy_threshold keeps adapting afterwards.

        Never raises - if no microphone is available, this is skipped
        and JARVIS continues starting up.
        """

        try:

            with sr.Microphone() as source:

                print("Calibrating microphone for ambient noise...")

                self.recognizer.adjust_for_ambient_noise(
                    source,
                    duration=config.AMBIENT_NOISE_DURATION
                )

        except Exception as error:

            print(f"Microphone calibration skipped: {error}")

    def listen(self, timeout=5, phrase_limit=8):
        """Listen once and return recognized text, or "" if nothing could
        be captured or understood. Never raises."""

        audio = self._capture_audio(timeout, phrase_limit)

        if audio is None:
            return ""

        return self._recognize(audio)

    def listen_with_retry(self, timeout=5, phrase_limit=8, retries=None):
        """Like listen(), but if nothing is understood, asks the user to
        repeat and tries again, up to `retries` extra times (default:
        config.COMMAND_RECOGNITION_RETRIES)."""

        if retries is None:
            retries = config.COMMAND_RECOGNITION_RETRIES

        for attempt in range(retries + 1):

            result = self.listen(timeout=timeout, phrase_limit=phrase_limit)

            if result:
                return result

            if attempt < retries:
                self.voice.speak("Sorry, I didn't catch that. Please repeat.")

        return ""

    def _capture_audio(self, timeout, phrase_limit):

        try:

            with sr.Microphone() as source:

                print("Listening...")

                return self.recognizer.listen(
                    source,
                    timeout=timeout,
                    phrase_time_limit=phrase_limit
                )

        except sr.WaitTimeoutError:
            return None

        except Exception as error:

            print(f"Microphone error: {error}")
            return None

    def _recognize(self, audio):

        print("Processing...")

        for attempt in range(config.SPEECH_API_RETRIES + 1):

            try:

                command = self.recognizer.recognize_google(
                    audio,
                    language=config.RECOGNITION_LANGUAGE
                )

                command = command.lower().strip()

                print(f"You: {command}")

                return command

            except sr.UnknownValueError:

                print("Could not understand the speech.")
                return ""

            except sr.RequestError as error:

                print(f"Speech recognition error: {error}")

                # Transient network/API errors: retry recognition on the
                # SAME captured audio (no need to make the user repeat
                # themselves) before giving up.
                if attempt < config.SPEECH_API_RETRIES:
                    time.sleep(config.SPEECH_API_RETRY_DELAY)
                    continue

                self._announce_request_error()
                return ""

        return ""

    def _announce_request_error(self):
        """Speak the connectivity warning, but not more than once per
        config.REQUEST_ERROR_ANNOUNCE_COOLDOWN seconds, so a prolonged
        outage doesn't repeat the announcement on every listen cycle."""

        now = time.monotonic()

        if (
            self._last_request_error_announcement is not None
            and now - self._last_request_error_announcement
            < config.REQUEST_ERROR_ANNOUNCE_COOLDOWN
        ):
            return

        self._last_request_error_announcement = now

        self.voice.speak(
            "I am having trouble connecting to speech recognition."
        )
