"""
Unit tests for Week 2 (Days 8-9) Audio Device Adapter & Permission States.
Owner: Satwik A (feature/audio-vad)

Verifies:
- Mock device discovery (default mock device list)
- Device selection (by ID, selecting non-existent device, selecting unavailable device)
- Permission states (GRANTED, DENIED, UNAVAILABLE, PROMPT)
- Permission state transitions and auto-grant simulation
- Rejection of device listing, selection, and stream creation on DENIED/UNAVAILABLE/PROMPT
- Device compatibility checks (sample rates, channels) when creating AudioSource
- Clean error envelope serialization for device exceptions
- Fallback selection when devices are removed or made unavailable
"""
import pytest

from packages.audio.device import (
    AudioDeviceAdapter,
    DeviceInfo,
    MockAudioDeviceAdapter,
    PermissionState,
)
from packages.audio.exceptions import (
    AudioDeviceError,
    DeviceNotFoundError,
    DevicePermissionError,
)
from packages.audio.mock_mic import AudioSource
from packages.audio.models import AudioConfig


def test_default_device_discovery():
    """Verify default mock adapter exposes realistic mock devices and default selection."""
    adapter = MockAudioDeviceAdapter()
    devices = adapter.list_devices()

    assert len(devices) == 3
    default_dev = adapter.get_selected_device()
    assert default_dev.is_default is True
    assert default_dev.device_id == "mock-default-mic"
    assert default_dev.is_available is True
    assert 16000 in default_dev.sample_rates


def test_device_selection_success():
    """Verify selecting a valid device switches selected device."""
    adapter = MockAudioDeviceAdapter()
    selected = adapter.select_device("mock-usb-headset")

    assert selected.device_id == "mock-usb-headset"
    assert adapter.get_selected_device().device_id == "mock-usb-headset"


def test_device_selection_nonexistent():
    """Verify selecting a non-existent device raises DeviceNotFoundError."""
    adapter = MockAudioDeviceAdapter()
    with pytest.raises(DeviceNotFoundError) as exc_info:
        adapter.select_device("non-existent-device-xyz")

    assert "non-existent-device-xyz" in str(exc_info.value)
    assert exc_info.value.code == "AUDIO_DEVICE_NOT_FOUND"


def test_device_selection_unavailable():
    """Verify selecting an unavailable device raises DeviceNotFoundError."""
    adapter = MockAudioDeviceAdapter()
    adapter.set_device_availability("mock-studio-mic", False)

    with pytest.raises(DeviceNotFoundError) as exc_info:
        adapter.select_device("mock-studio-mic")

    assert "unavailable" in str(exc_info.value)


def test_permission_state_denied():
    """Verify DENIED permission prevents listing, selecting, and streaming."""
    adapter = MockAudioDeviceAdapter(initial_permission=PermissionState.DENIED)
    assert adapter.get_permission_state() == PermissionState.DENIED

    with pytest.raises(DevicePermissionError) as exc_list:
        adapter.list_devices()
    assert exc_list.value.code == "AUDIO_PERMISSION_DENIED"

    with pytest.raises(DevicePermissionError) as exc_sel:
        adapter.select_device("mock-default-mic")
    assert exc_sel.value.code == "AUDIO_PERMISSION_DENIED"

    with pytest.raises(DevicePermissionError) as exc_src:
        adapter.create_source()
    assert exc_src.value.code == "AUDIO_PERMISSION_DENIED"


def test_permission_state_unavailable():
    """Verify UNAVAILABLE permission prevents listing, selecting, and streaming."""
    adapter = MockAudioDeviceAdapter(initial_permission=PermissionState.UNAVAILABLE)

    with pytest.raises(DevicePermissionError) as exc_list:
        adapter.list_devices()
    assert exc_list.value.code == "AUDIO_DEVICE_UNAVAILABLE"

    with pytest.raises(DevicePermissionError) as exc_sel:
        adapter.select_device("mock-default-mic")
    assert exc_sel.value.code == "AUDIO_DEVICE_UNAVAILABLE"

    with pytest.raises(DevicePermissionError) as exc_src:
        adapter.create_source()
    assert exc_src.value.code == "AUDIO_DEVICE_UNAVAILABLE"


def test_permission_state_prompt_and_request():
    """Verify PROMPT permission state and request_permission behavior."""
    adapter = MockAudioDeviceAdapter(
        initial_permission=PermissionState.PROMPT,
        auto_grant=False,
    )
    assert adapter.get_permission_state() == PermissionState.PROMPT

    # Cannot create source while in PROMPT state without grant
    with pytest.raises(DevicePermissionError) as exc_src:
        adapter.create_source()
    assert exc_src.value.code == "AUDIO_PERMISSION_PROMPT"

    # With auto_grant=False, request_permission leaves it in PROMPT
    state = adapter.request_permission()
    assert state == PermissionState.PROMPT

    # Enable auto_grant or manually set to GRANTED
    adapter.set_permission_state(PermissionState.GRANTED)
    assert adapter.get_permission_state() == PermissionState.GRANTED

    # Now create_source succeeds and returns AudioSource instance
    source = adapter.create_source()
    assert isinstance(source, AudioSource)


def test_create_source_returns_audio_source_abstraction():
    """Verify AudioDeviceAdapter.create_source() returns the AudioSource abstraction."""
    adapter: AudioDeviceAdapter = MockAudioDeviceAdapter()
    source = adapter.create_source()

    assert isinstance(source, AudioSource)
    with source:
        frame = source.read_frame()
        assert frame is not None


def test_create_source_unsupported_config_rejection():
    """Verify creating source with config exceeding device capabilities is rejected."""
    custom_device = DeviceInfo(
        device_id="narrow-band-mic",
        name="Narrowband Intercom",
        is_default=True,
        sample_rates=[8000],
        channels=1,
    )
    adapter = MockAudioDeviceAdapter(initial_devices=[custom_device])

    # 16000 Hz config exceeds device capability (only 8000 Hz supported)
    cfg16k = AudioConfig(sample_rate=16000, channels=1)
    with pytest.raises(AudioDeviceError) as exc_sr:
        adapter.create_source(config=cfg16k)
    assert "does not support sample rate 16000" in str(exc_sr.value)
    assert exc_sr.value.code == "AUDIO_DEVICE_UNSUPPORTED_CONFIG"

    # Stereo config exceeds device single channel
    cfg_stereo = AudioConfig(sample_rate=8000, channels=2)
    with pytest.raises(AudioDeviceError) as exc_ch:
        adapter.create_source(config=cfg_stereo)
    assert "supports at most 1 channel(s), got 2" in str(exc_ch.value)


def test_device_removal_and_selection_fallback():
    """Verify removing selected device updates selection state and fallback."""
    # Adapter initialized with non-default first device
    dev1 = DeviceInfo(device_id="d1", name="Mic 1", is_default=False, is_available=True)
    dev2 = DeviceInfo(device_id="d2", name="Mic 2", is_default=False, is_available=True)
    adapter = MockAudioDeviceAdapter(initial_devices=[dev1, dev2])
    assert adapter.get_selected_device().device_id == "d1"

    # Remove currently selected device d1 -> falls back to d2
    adapter.remove_device("d1")
    assert adapter.get_selected_device().device_id == "d2"

    # Remove d2 -> now empty list
    adapter.remove_device("d2")
    with pytest.raises(DeviceNotFoundError):
        adapter.get_selected_device()


def test_get_selected_device_when_selected_becomes_unavailable():
    """Verify get_selected_device raises DeviceNotFoundError if selected device becomes unavailable."""
    adapter = MockAudioDeviceAdapter()
    adapter.set_device_availability("mock-default-mic", False)

    with pytest.raises(DeviceNotFoundError) as exc_info:
        adapter.get_selected_device()
    assert "currently unavailable" in str(exc_info.value)


def test_add_custom_device():
    """Verify adding a new device dynamically."""
    adapter = MockAudioDeviceAdapter()
    new_dev = DeviceInfo(device_id="new-mic-1", name="External Mic", channels=2)
    adapter.add_device(new_dev)

    devices = adapter.list_devices()
    assert any(d.device_id == "new-mic-1" for d in devices)
    selected = adapter.select_device("new-mic-1")
    assert selected.device_id == "new-mic-1"


def test_abstract_methods_raise_not_implemented():
    """Verify base AudioDeviceAdapter abstract methods."""
    class DummyAdapter(AudioDeviceAdapter):
        def get_permission_state(self):
            return super().get_permission_state()

        def request_permission(self):
            return super().request_permission()

        def list_devices(self):
            return super().list_devices()

        def get_selected_device(self):
            return super().get_selected_device()

        def select_device(self, device_id: str):
            return super().select_device(device_id)

        def create_source(self, config=None):
            return super().create_source(config)

    dummy = DummyAdapter()
    with pytest.raises(NotImplementedError):
        dummy.get_permission_state()
    with pytest.raises(NotImplementedError):
        dummy.request_permission()
    with pytest.raises(NotImplementedError):
        dummy.list_devices()
    with pytest.raises(NotImplementedError):
        dummy.get_selected_device()
    with pytest.raises(NotImplementedError):
        dummy.select_device("dev-1")
    with pytest.raises(NotImplementedError):
        dummy.create_source()


def test_device_error_envelope_serialization():
    """Verify AudioDeviceError family conforms to SDK-9 error envelope."""
    err = DevicePermissionError(
        message="Microphone permission was denied by user",
        code="AUDIO_PERMISSION_DENIED",
        retryable=False,
        correlation_id="corr-perm-123",
        details={"os_error": "EPERM"},
    )
    envelope = err.to_envelope()
    assert envelope["code"] == "AUDIO_PERMISSION_DENIED"
    assert envelope["message_safe_for_user"] == "Microphone permission was denied by user"
    assert envelope["retryable"] is False
    assert envelope["correlation_id"] == "corr-perm-123"
    assert envelope["details_redacted"] == {"os_error": "EPERM"}
