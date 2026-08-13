import pyttsx3

import config


class Voice:
    """Wraps pyttsx3 initialization and speaking."""

    def __init__(self):

        self.engine = pyttsx3.init()
        self.engine.setProperty("rate", config.TTS_RATE)
        self.engine.setProperty("volume", config.TTS_VOLUME)

    def speak(self, text):

        print(f"JARVIS: {text}")

        self.engine.say(text)
        self.engine.runAndWait()
