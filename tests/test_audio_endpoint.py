from unittest.mock import MagicMock, patch

import pytest

import audio_endpoint


# ---------------------------------------------------------------------
# set_volume_percent() / set_mute() - the public API volume_control.py
# calls. Mocked at _get_endpoint_volume() so no real COM object is ever
# acquired and no real audio device is ever touched.
# ---------------------------------------------------------------------

def test_set_volume_percent_converts_40_to_0_4_scalar():
    fake_endpoint = MagicMock()

    with patch("audio_endpoint._get_endpoint_volume", return_value=fake_endpoint):
        audio_endpoint.set_volume_percent(40)

    fake_endpoint.SetMasterVolumeLevelScalar.assert_called_once_with(0.4, None)


def test_set_volume_percent_0_converts_to_0_0_scalar():
    fake_endpoint = MagicMock()

    with patch("audio_endpoint._get_endpoint_volume", return_value=fake_endpoint):
        audio_endpoint.set_volume_percent(0)

    fake_endpoint.SetMasterVolumeLevelScalar.assert_called_once_with(0.0, None)


def test_set_volume_percent_100_converts_to_1_0_scalar():
    fake_endpoint = MagicMock()

    with patch("audio_endpoint._get_endpoint_volume", return_value=fake_endpoint):
        audio_endpoint.set_volume_percent(100)

    fake_endpoint.SetMasterVolumeLevelScalar.assert_called_once_with(1.0, None)


def test_set_mute_true_calls_setmute_true():
    fake_endpoint = MagicMock()

    with patch("audio_endpoint._get_endpoint_volume", return_value=fake_endpoint):
        audio_endpoint.set_mute(True)

    fake_endpoint.SetMute.assert_called_once_with(True, None)


def test_set_mute_false_calls_setmute_false():
    fake_endpoint = MagicMock()

    with patch("audio_endpoint._get_endpoint_volume", return_value=fake_endpoint):
        audio_endpoint.set_mute(False)

    fake_endpoint.SetMute.assert_called_once_with(False, None)


def test_set_mute_coerces_truthy_non_bool_to_bool():
    fake_endpoint = MagicMock()

    with patch("audio_endpoint._get_endpoint_volume", return_value=fake_endpoint):
        audio_endpoint.set_mute(1)

    fake_endpoint.SetMute.assert_called_once_with(True, None)


# ---------------------------------------------------------------------
# COM/API errors are not swallowed here - audio_endpoint.py is a thin,
# honest wrapper; volume_control.py is responsible for catching and
# reporting gracefully (see test_volume_control.py for that coverage).
# ---------------------------------------------------------------------

def test_set_volume_percent_propagates_os_error():
    fake_endpoint = MagicMock()
    fake_endpoint.SetMasterVolumeLevelScalar.side_effect = OSError("no device")

    with patch("audio_endpoint._get_endpoint_volume", return_value=fake_endpoint):
        with pytest.raises(OSError):
            audio_endpoint.set_volume_percent(40)


def test_set_mute_propagates_com_error():
    import comtypes

    fake_endpoint = MagicMock()
    fake_endpoint.SetMute.side_effect = comtypes.COMError(
        -2147023728, "text", ("details",)
    )

    with patch("audio_endpoint._get_endpoint_volume", return_value=fake_endpoint):
        with pytest.raises(comtypes.COMError):
            audio_endpoint.set_mute(True)


# ---------------------------------------------------------------------
# _get_endpoint_volume() acquisition chain - every collaborator mocked
# at the point of use (comtypes.CoCreateInstance, ctypes.cast), so this
# proves the wiring (which functions get called, with which arguments,
# in which order) without ever making a real COM/device call.
# ---------------------------------------------------------------------

def test_get_endpoint_volume_wiring_is_fully_mocked_no_real_com_call():
    fake_device = MagicMock()
    fake_enumerator = MagicMock()
    fake_enumerator.GetDefaultAudioEndpoint.return_value = fake_device
    fake_interface_ptr = MagicMock()
    fake_device.Activate.return_value = fake_interface_ptr
    fake_casted = MagicMock()

    with patch(
        "audio_endpoint.comtypes.CoCreateInstance", return_value=fake_enumerator
    ) as mock_create, patch(
        "audio_endpoint.ctypes.cast", return_value=fake_casted
    ) as mock_cast:
        result = audio_endpoint._get_endpoint_volume()

    mock_create.assert_called_once_with(
        audio_endpoint.CLSID_MMDeviceEnumerator,
        audio_endpoint.IMMDeviceEnumerator,
        audio_endpoint.comtypes.CLSCTX_INPROC_SERVER,
    )
    fake_enumerator.GetDefaultAudioEndpoint.assert_called_once_with(
        audio_endpoint.E_RENDER, audio_endpoint.E_CONSOLE
    )
    fake_device.Activate.assert_called_once_with(
        audio_endpoint.IAudioEndpointVolume._iid_,
        audio_endpoint.CLSCTX_ALL,
        None,
    )
    mock_cast.assert_called_once_with(
        fake_interface_ptr, audio_endpoint.POINTER(audio_endpoint.IAudioEndpointVolume)
    )
    assert result is fake_casted


def test_set_volume_percent_uses_get_endpoint_volume_not_a_cached_object():
    """Defense-in-depth structural check: set_volume_percent() must
    acquire the interface via _get_endpoint_volume() each call, not via
    some module-level cached/persistent COM object - see module
    docstring for why a fresh, short-lived interface is used."""

    fake_endpoint = MagicMock()

    with patch(
        "audio_endpoint._get_endpoint_volume", return_value=fake_endpoint
    ) as mock_get:
        audio_endpoint.set_volume_percent(10)
        audio_endpoint.set_volume_percent(20)

    assert mock_get.call_count == 2
