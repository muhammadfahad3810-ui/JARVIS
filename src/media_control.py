"""Media playback control via the standard Windows multimedia keys."""

import input_control


def play_pause(voice):

    voice.speak("Toggling play and pause.")

    input_control.press_key(input_control.VK_MEDIA_PLAY_PAUSE)


def next_track(voice):

    voice.speak("Playing the next track.")

    input_control.press_key(input_control.VK_MEDIA_NEXT_TRACK)


def previous_track(voice):

    voice.speak("Playing the previous track.")

    input_control.press_key(input_control.VK_MEDIA_PREV_TRACK)


def handle(command, voice):
    """Try to handle a media-control command. Returns True if handled."""

    if "next track" in command or "next song" in command:
        next_track(voice)
        return True

    if (
        "previous track" in command
        or "previous song" in command
        or "last track" in command
    ):
        previous_track(voice)
        return True

    if "play" in command or "pause" in command:
        play_pause(voice)
        return True

    return False
