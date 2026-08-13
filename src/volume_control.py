"""System volume control.

"volume up"/"volume down" remain unchanged since Phase 3: relative
nudges via the standard Windows multimedia keys (input_control.py) -
one step per invocation, size decided by the OS.

"mute"/"unmute" and the new "set volume to <N> percent" (Phase 7) go
through audio_endpoint.py's Core Audio (IAudioEndpointVolume) wrapper
instead, for true absolute control:

PHASE 7 BEHAVIOR CHANGE: "mute" and "unmute" used to both just press
the single Windows multimedia mute-TOGGLE key (VK_VOLUME_MUTE) - there
is no dedicated "force unmute" multimedia key, so saying "unmute" while
already unmuted used to mute the system instead. As of Phase 7, "mute"
and "unmute" call IAudioEndpointVolume.SetMute(True/False) directly,
so each is now idempotent and does exactly what it says regardless of
the current state.
"""

import re

import comtypes

import audio_endpoint
import input_control


SET_VOLUME_PATTERN = re.compile(r"^set volume to (\d{1,3})$")


def volume_up(voice):

    voice.speak("Increasing the volume.")

    input_control.press_key(input_control.VK_VOLUME_UP)


def volume_down(voice):

    voice.speak("Decreasing the volume.")

    input_control.press_key(input_control.VK_VOLUME_DOWN)


def set_volume(voice, percent):
    """Set the true, absolute system volume to `percent` (0-100) via
    Core Audio. Rejects (never clamps) anything outside 0-100 - defense
    in depth: command_parser.py already only ever produces this
    canonical command for an already-validated 0-100 value, but this
    function doesn't trust that it's the only caller, the same way
    window_control.py's by-name action functions never trust that
    their caller already validated the target (see
    resolve_window_target())."""

    if not (0 <= percent <= 100):
        voice.speak("I can only set the volume between 0 and 100 percent.")
        return

    voice.speak(f"Setting volume to {percent} percent.")

    try:
        audio_endpoint.set_volume_percent(percent)
    except (OSError, comtypes.COMError):
        voice.speak("I couldn't change the volume.")


def mute(voice):
    """True, absolute mute via Core Audio - idempotent (always mutes,
    regardless of current state). See module docstring: this replaces
    the old multimedia-key toggle behavior from Phase 6 and earlier."""

    voice.speak("Muting the volume.")

    try:
        audio_endpoint.set_mute(True)
    except (OSError, comtypes.COMError):
        voice.speak("I couldn't mute the volume.")


def unmute(voice):
    """True, absolute unmute via Core Audio - idempotent (always
    unmutes, regardless of current state). See module docstring: this
    replaces the old multimedia-key toggle behavior from Phase 6 and
    earlier."""

    voice.speak("Unmuting the volume.")

    try:
        audio_endpoint.set_mute(False)
    except (OSError, comtypes.COMError):
        voice.speak("I couldn't unmute the volume.")


def handle(command, voice):
    """Try to handle a volume-control command. Returns True if handled."""

    match = SET_VOLUME_PATTERN.match(command)

    if match:
        set_volume(voice, int(match.group(1)))
        return True

    if "volume up" in command:
        volume_up(voice)
        return True

    if "volume down" in command:
        volume_down(voice)
        return True

    if "unmute" in command:
        unmute(voice)
        return True

    if "mute" in command:
        mute(voice)
        return True

    return False
