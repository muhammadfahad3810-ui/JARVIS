import os
import subprocess
import webbrowser


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

    # CHROME
    if "chrome" in command:
        open_chrome(voice)
        return True

    # EDGE
    if "edge" in command:
        open_edge(voice)
        return True

    return False
