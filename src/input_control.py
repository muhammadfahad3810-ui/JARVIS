"""Low-level synthetic keyboard input via the Windows user32 API.

Used by window_control.py, volume_control.py, media_control.py, and
keyboard_control.py to simulate fixed, known key presses (media keys,
Alt+Tab, Ctrl+C, etc). This module never accepts arbitrary text or
commands to type - only a fixed, hardcoded set of virtual key codes
defined below are ever sent.
"""

import ctypes
import time

user32 = ctypes.windll.user32

KEYEVENTF_KEYUP = 0x0002

# Virtual key codes (Windows Virtual-Key Codes reference)
VK_RETURN = 0x0D
VK_TAB = 0x09
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_CONTROL = 0x11
VK_MENU = 0x12          # Alt
VK_LWIN = 0x5B

VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3

VK_KEY_A = 0x41
VK_KEY_C = 0x43
VK_KEY_D = 0x44
VK_KEY_V = 0x56
VK_KEY_Z = 0x5A

HOLD_SECONDS = 0.02


def press_key(vk_code):
    """Press and release a single virtual key."""

    user32.keybd_event(vk_code, 0, 0, 0)
    time.sleep(HOLD_SECONDS)
    user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)


def press_key_combo(*vk_codes):
    """Press multiple virtual keys together (e.g. Ctrl+C), holding all
    of them down, then releasing in reverse order."""

    for vk in vk_codes:
        user32.keybd_event(vk, 0, 0, 0)

    time.sleep(HOLD_SECONDS)

    for vk in reversed(vk_codes):
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
