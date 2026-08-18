"""Low-level synthetic keyboard and mouse input via the Windows user32
API.

Used by window_control.py, volume_control.py, media_control.py,
keyboard_control.py, web_control.py, and mouse_control.py to simulate
fixed, known key presses/mouse actions (media keys, Alt+Tab, Ctrl+C,
a left click, etc). This module never accepts arbitrary text or
commands to type - only a fixed, hardcoded set of virtual key codes/
mouse actions defined below are ever sent, and mouse movement is
always a fixed, hardcoded pixel delta (see mouse_control.py), never a
coordinate derived from spoken text.

Keyboard input is injected via SendInput (the modern, Microsoft-
recommended replacement for the legacy keybd_event - see
https://learn.microsoft.com/windows/win32/api/winuser/nf-winuser-keybd_event,
"This function has been superseded. Use SendInput instead."). Like
keybd_event, SendInput delivers to whatever window currently has
keyboard focus - it does NOT target a specific window/process, and
this module never tries to (see mouse/keyboard_control.py/web_control.
py's own docstrings: every action here operates on "whatever has
focus", by design, never a hardcoded target). Two things SendInput
gives that keybd_event did not: (1) a genuine per-call success signal
(the number of events it actually queued into the input stream - 0
means the OS rejected/blocked the injection, e.g. UIPI blocking input
into a higher-integrity-level window), propagated up through press_
key()/press_key_combo()'s own return value so callers can tell a
successful injection from a silent no-op instead of always assuming
success; and (2) correct extended-key flagging (KEYEVENTF_EXTENDEDKEY)
for the arrow/paging keys in EXTENDED_VK_CODES below - without it, the
OS can generate the numpad-cluster scan code instead of the dedicated
navigation key's scan code, which some applications (browsers
included) distinguish between.
"""

import ctypes
import time

user32 = ctypes.windll.user32

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1
ULONG_PTR = ctypes.c_size_t

# Virtual key codes (Windows Virtual-Key Codes reference)
VK_RETURN = 0x0D
VK_TAB = 0x09
VK_BACK = 0x08          # Backspace
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_MENU = 0x12          # Alt
VK_LWIN = 0x5B
VK_PRIOR = 0x21         # Page Up
VK_NEXT = 0x22          # Page Down
VK_LEFT = 0x25
VK_RIGHT = 0x27
VK_F5 = 0x74

VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3

VK_KEY_A = 0x41
VK_KEY_C = 0x43
VK_KEY_D = 0x44
VK_KEY_T = 0x54
VK_KEY_V = 0x56
VK_KEY_W = 0x57
VK_KEY_X = 0x58
VK_KEY_Z = 0x5A

HOLD_SECONDS = 0.02

# Small stagger between each key-down (and each key-up) within a
# combo - chorded shortcuts (Ctrl+T, Ctrl+Shift+Tab, ...) are more
# reliably recognized by the receiving application when the modifier's
# keydown is fully processed before the next key's keydown arrives,
# rather than firing both back-to-back with zero delay.
COMBO_KEY_STAGGER_SECONDS = 0.03

# Virtual-key codes that are part of the "extended" key set on a
# standard keyboard (the dedicated arrow/paging/navigation cluster, as
# opposed to the numpad) - these need KEYEVENTF_EXTENDEDKEY set so the
# OS generates their correct scan code, matching what a real keyboard
# sends (VK_PRIOR/VK_NEXT are used by keyboard_control.scroll_up()/
# scroll_down(), VK_LEFT/VK_RIGHT by web_control.go_back()/
# go_forward()'s Alt+Left/Alt+Right). Only the extended keys this
# module actually defines/uses.
EXTENDED_VK_CODES = frozenset({VK_PRIOR, VK_NEXT, VK_LEFT, VK_RIGHT})

# Mouse event flags (mouse_event() reference) - only a plain left/right
# click is ever synthesized, never a drag or arbitrary button mask.
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ULONG_PTR),
    ]


# MOUSEINPUT/HARDWAREINPUT are never populated by this module (only
# ki/KEYBDINPUT is) - they exist here ONLY so _INPUTunion's computed
# size matches the real Win32 INPUT union exactly (its largest member,
# MOUSEINPUT, is bigger than KEYBDINPUT). This is load-bearing, not
# decorative: SendInput validates the cbSize argument against its own
# internal, fixed idea of sizeof(INPUT) and silently rejects the whole
# call (returns 0, injecting nothing) if the struct this module passes
# is a different size - which a union defined with ONLY ki would be.
class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_ushort),
        ("wParamH", ctypes.c_ushort),
    ]


class _INPUTunion(ctypes.Union):
    _fields_ = [
        ("mi", _MOUSEINPUT),
        ("ki", _KEYBDINPUT),
        ("hi", _HARDWAREINPUT),
    ]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("union", _INPUTunion)]


def _send_key_event(vk_code, key_up):
    """Inject one key-down or key-up event for `vk_code` via SendInput.
    Returns True if the OS accepted the event into the input stream
    (SendInput's return value - the count of events it actually
    queued), False otherwise (e.g. blocked by UIPI)."""

    flags = KEYEVENTF_KEYUP if key_up else 0

    if vk_code in EXTENDED_VK_CODES:
        flags |= KEYEVENTF_EXTENDEDKEY

    event = _INPUT(
        type=INPUT_KEYBOARD,
        union=_INPUTunion(ki=_KEYBDINPUT(
            wVk=vk_code, wScan=0, dwFlags=flags, time=0, dwExtraInfo=0
        )),
    )

    sent = user32.SendInput(1, ctypes.pointer(event), ctypes.sizeof(_INPUT))

    return sent == 1


def press_key(vk_code):
    """Press and release a single virtual key.

    Returns True if both the key-down and key-up events were accepted
    by the OS into the input stream, False otherwise. This is NOT a
    guarantee the target application acted on the key (SendInput has
    no way to know that), only that the injection itself wasn't
    rejected outright - callers should still treat False as a strong
    "this almost certainly did not reach the target application"
    signal, since a healthy, unblocked injection essentially always
    returns True.
    """

    down_ok = _send_key_event(vk_code, key_up=False)
    time.sleep(HOLD_SECONDS)
    up_ok = _send_key_event(vk_code, key_up=True)

    return down_ok and up_ok


def press_key_combo(*vk_codes):
    """Press multiple virtual keys together (e.g. Ctrl+C), holding all
    of them down (each key-down staggered by COMBO_KEY_STAGGER_SECONDS
    so the receiving application reliably registers the chord), then
    releasing in reverse order. Returns True only if every key-down and
    key-up event in the combo was accepted by the OS - see press_key()'s
    own docstring for what that guarantee does and doesn't cover.
    """

    ok = True

    for vk in vk_codes:
        ok = _send_key_event(vk, key_up=False) and ok
        time.sleep(COMBO_KEY_STAGGER_SECONDS)

    time.sleep(HOLD_SECONDS)

    for vk in reversed(vk_codes):
        ok = _send_key_event(vk, key_up=True) and ok
        time.sleep(COMBO_KEY_STAGGER_SECONDS)

    return ok


def click_mouse():
    """Press and release the left mouse button at the current cursor
    position."""

    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(HOLD_SECONDS)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def right_click_mouse():
    """Press and release the right mouse button at the current cursor
    position."""

    user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
    time.sleep(HOLD_SECONDS)
    user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)


def get_cursor_pos():
    """Return the current (x, y) cursor position."""

    point = _POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def move_mouse_by(dx, dy):
    """Move the cursor by a fixed (dx, dy) pixel offset from its
    current position."""

    x, y = get_cursor_pos()
    user32.SetCursorPos(x + dx, y + dy)
