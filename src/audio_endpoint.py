"""Windows Core Audio (WASAPI) volume/mute control via comtypes.

Talks directly to IAudioEndpointVolume on the current default playback
("render") endpoint to provide true absolute volume (0.0-1.0 scalar)
and true mute (set, not toggle) - replacing the old multimedia-key
toggle approach in volume_control.py (Phase 6 and earlier).

Implemented with `comtypes` - already an installed, declared project
dependency (see requirements.txt), and already used elsewhere in this
process by pyttsx3's SAPI5 driver - directly against the public,
stable COM interfaces declared in mmdeviceapi.h / endpointvolume.h.
No pycaw or other third-party wrapper is used or needed.

Only the interface methods this module actually calls are exposed
through a narrow public API: set_volume_percent() and set_mute().
Range/type validation of the percent argument is the caller's
responsibility (see volume_control.py) - this module trusts its
input and focuses purely on the COM plumbing.

COM initialization: comtypes itself calls CoInitializeEx() once, at
first import, for whichever thread imports it first (see comtypes/
__init__.py), and registers an atexit hook to call CoUninitialize()
at interpreter shutdown. pyttsx3's SAPI5 driver (voice.py) already
imports comtypes, so by the time any volume command reaches this
module, COM is already initialized on this (single, synchronous)
thread - this module deliberately does NOT call CoInitialize() or
CoUninitialize() itself, to avoid duplicating or interfering with
comtypes' own already-correct, process-wide lifecycle.

COM object lifetime: _get_endpoint_volume() acquires a fresh
IAudioEndpointVolume interface on every call and returns it; no
interface pointer is cached or kept alive across calls. JARVIS issues
at most one volume command at a time (synchronous command loop), so
there is no benefit to holding a persistent COM object open, and a
short-lived one is simpler to reason about and avoids the object
becoming stale if the default playback device changes between calls.
The interface pointer is released automatically by comtypes/Python's
normal reference counting once it goes out of scope.

Every function here can raise OSError or comtypes.COMError if the
underlying COM call fails (e.g. no default playback device present).
Callers (volume_control.py) are responsible for catching these and
reporting gracefully - the same pattern used elsewhere in this project
for real-world failures (see e.g. speech.py's microphone error
handling).
"""

import ctypes
from ctypes import POINTER, c_float, c_void_p
from ctypes.wintypes import BOOL, DWORD

import comtypes
from comtypes import COMMETHOD, GUID, HRESULT, IUnknown


CLSID_MMDeviceEnumerator = GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
IID_IMMDeviceEnumerator = GUID("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
IID_IMMDevice = GUID("{D666063F-1587-4E43-81F1-B948E807363F}")
IID_IAudioEndpointVolume = GUID("{5CDF2C82-841E-4546-9722-0CF74078229A}")

# EDataFlow / ERole enum values (mmdeviceapi.h) - eRender / eConsole.
E_RENDER = 0
E_CONSOLE = 0

# CLSCTX_INPROC_SERVER | CLSCTX_INPROC_HANDLER | CLSCTX_LOCAL_SERVER |
# CLSCTX_REMOTE_SERVER - i.e. CLSCTX_ALL, used for IMMDevice.Activate().
CLSCTX_ALL = 23


class IMMDevice(IUnknown):
    """Only Activate() (vtable slot 0) is declared - the only IMMDevice
    method this module needs."""

    _iid_ = IID_IMMDevice
    _methods_ = [
        COMMETHOD(
            [], HRESULT, "Activate",
            (["in"], POINTER(GUID), "iid"),
            (["in"], DWORD, "dwClsCtx"),
            (["in"], c_void_p, "pActivationParams"),
            (["out"], POINTER(c_void_p), "ppInterface"),
        ),
    ]


class IMMDeviceEnumerator(IUnknown):
    """EnumAudioEndpoints (vtable slot 0) is declared but never called -
    it exists only so GetDefaultAudioEndpoint (slot 1) lands at its
    correct vtable offset. comtypes assigns vtable slots strictly by
    _methods_ list order, so every preceding real method must be
    present even when unused."""

    _iid_ = IID_IMMDeviceEnumerator
    _methods_ = [
        COMMETHOD(
            [], HRESULT, "EnumAudioEndpoints",
            (["in"], DWORD, "dataFlow"),
            (["in"], DWORD, "dwStateMask"),
            (["out"], POINTER(c_void_p), "ppDevices"),
        ),
        COMMETHOD(
            [], HRESULT, "GetDefaultAudioEndpoint",
            (["in"], DWORD, "dataFlow"),
            (["in"], DWORD, "role"),
            (["out"], POINTER(POINTER(IMMDevice)), "ppEndpoint"),
        ),
    ]


class IAudioEndpointVolume(IUnknown):
    """Declares every vtable slot up to and including GetMute (slot 12)
    in their real endpointvolume.h order, so the two slots this module
    actually calls - SetMasterVolumeLevelScalar (4) and SetMute (11) -
    land at the correct offsets (see IMMDeviceEnumerator's docstring
    for why the unused ones in between can't be skipped). Slots after
    GetMute (per-channel step up/down, hardware support, volume range)
    are never called and are omitted entirely - nothing after the last
    declared method is needed."""

    _iid_ = IID_IAudioEndpointVolume
    _methods_ = [
        COMMETHOD([], HRESULT, "RegisterControlChangeNotify",
                  (["in"], c_void_p, "pNotify")),
        COMMETHOD([], HRESULT, "UnregisterControlChangeNotify",
                  (["in"], c_void_p, "pNotify")),
        COMMETHOD([], HRESULT, "GetChannelCount",
                  (["out"], POINTER(ctypes.c_uint), "pnChannelCount")),
        COMMETHOD([], HRESULT, "SetMasterVolumeLevel",
                  (["in"], c_float, "fLevelDB"),
                  (["in"], POINTER(GUID), "pguidEventContext")),
        COMMETHOD([], HRESULT, "SetMasterVolumeLevelScalar",
                  (["in"], c_float, "fLevel"),
                  (["in"], POINTER(GUID), "pguidEventContext")),
        COMMETHOD([], HRESULT, "GetMasterVolumeLevel",
                  (["out"], POINTER(c_float), "pfLevelDB")),
        COMMETHOD([], HRESULT, "GetMasterVolumeLevelScalar",
                  (["out"], POINTER(c_float), "pfLevel")),
        COMMETHOD([], HRESULT, "SetChannelVolumeLevel",
                  (["in"], DWORD, "nChannel"),
                  (["in"], c_float, "fLevelDB"),
                  (["in"], POINTER(GUID), "pguidEventContext")),
        COMMETHOD([], HRESULT, "SetChannelVolumeLevelScalar",
                  (["in"], DWORD, "nChannel"),
                  (["in"], c_float, "fLevel"),
                  (["in"], POINTER(GUID), "pguidEventContext")),
        COMMETHOD([], HRESULT, "GetChannelVolumeLevel",
                  (["in"], DWORD, "nChannel"),
                  (["out"], POINTER(c_float), "pfLevelDB")),
        COMMETHOD([], HRESULT, "GetChannelVolumeLevelScalar",
                  (["in"], DWORD, "nChannel"),
                  (["out"], POINTER(c_float), "pfLevel")),
        COMMETHOD([], HRESULT, "SetMute",
                  (["in"], BOOL, "bMute"),
                  (["in"], POINTER(GUID), "pguidEventContext")),
        COMMETHOD([], HRESULT, "GetMute",
                  (["out"], POINTER(BOOL), "pbMute")),
    ]


def _get_endpoint_volume():
    """Acquire a fresh IAudioEndpointVolume interface for the current
    default playback device. See module docstring for why this is not
    cached and why COM init/uninit is deliberately not handled here."""

    enumerator = comtypes.CoCreateInstance(
        CLSID_MMDeviceEnumerator,
        IMMDeviceEnumerator,
        comtypes.CLSCTX_INPROC_SERVER,
    )

    device = enumerator.GetDefaultAudioEndpoint(E_RENDER, E_CONSOLE)

    interface_ptr = device.Activate(
        IAudioEndpointVolume._iid_, CLSCTX_ALL, None
    )

    return ctypes.cast(interface_ptr, POINTER(IAudioEndpointVolume))


def set_volume_percent(percent):
    """Set the true, absolute master volume to `percent` (expected
    0-100) on the default playback device. Trusts its input - callers
    (volume_control.py) are responsible for range validation. Converts
    0-100 to the 0.0-1.0 scalar SetMasterVolumeLevelScalar expects."""

    endpoint_volume = _get_endpoint_volume()
    endpoint_volume.SetMasterVolumeLevelScalar(percent / 100.0, None)


def set_mute(muted):
    """Set the true, absolute mute state (True = muted, False =
    unmuted) on the default playback device - never a toggle."""

    endpoint_volume = _get_endpoint_volume()
    endpoint_volume.SetMute(bool(muted), None)
