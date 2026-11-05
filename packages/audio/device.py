"""
Audio device models, permission state representations, and adapter interfaces.
Owner: Satwik A (feature/audio-vad) - Week 2 (Days 8-9)

Provides:
- PermissionState: GRANTED, DENIED, UNAVAILABLE, PROMPT
- DeviceInfo: Pydantic v2 data model representing an audio input device
- AudioDeviceAdapter: Abstract provider-independent device contract
- MockAudioDeviceAdapter: Hardware-independent, deterministic mock device adapter
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from packages.audio.exceptions import (
    AudioDeviceError,
    DeviceNotFoundError,
    DevicePermissionError,
)
from packages.audio.mock_mic import AudioSource, MockMicrophoneSource
from packages.audio.models import AudioConfig


class PermissionState(str, Enum):
    """Audio capture device permission states."""
    GRANTED = "GRANTED"
    DENIED = "DENIED"
    UNAVAILABLE = "UNAVAILABLE"
    PROMPT = "PROMPT"


class DeviceInfo(BaseModel):
    """Data model representing an audio input/capture device."""
    model_config = ConfigDict(frozen=True, extra="ignore")

    device_id: str = Field(..., description="Unique hardware or virtual device identifier")
    name: str = Field(..., description="Human-readable device name")
    is_default: bool = Field(default=False, description="Whether this is the primary default input device")
    sample_rates: List[int] = Field(
        default_factory=lambda: [16000, 48000],
        description="Supported sample rates in Hz",
    )
    channels: int = Field(default=1, description="Max supported input channels")
    is_available: bool = Field(default=True, description="Whether the device is currently physically available")


class AudioDeviceAdapter(ABC):
    """Abstract interface for audio capture device discovery and selection."""

    @abstractmethod
    def get_permission_state(self) -> PermissionState:
        """Return the current permission state for microphone access."""
        raise NotImplementedError

    @abstractmethod
    def request_permission(self) -> PermissionState:
        """Request microphone permission from the user or operating system."""
        raise NotImplementedError

    @abstractmethod
    def list_devices(self) -> List[DeviceInfo]:
        """List all discovered input devices.

        Raises:
            DevicePermissionError: If permission is DENIED or UNAVAILABLE.
        """
        raise NotImplementedError

    @abstractmethod
    def get_selected_device(self) -> DeviceInfo:
        """Get the currently selected input device.

        Raises:
            DeviceNotFoundError: If no device is selected or available.
        """
        raise NotImplementedError

    @abstractmethod
    def select_device(self, device_id: str) -> DeviceInfo:
        """Select an input device by device_id.

        Raises:
            DeviceNotFoundError: If device_id is not in available devices.
            DevicePermissionError: If permission has not been granted.
        """
        raise NotImplementedError

    @abstractmethod
    def create_source(self, config: Optional[AudioConfig] = None) -> AudioSource:
        """Create an audio stream source from the selected device.

        Raises:
            DevicePermissionError: If permission is DENIED or UNAVAILABLE.
            AudioDeviceError: If device cannot be accessed.
        """
        raise NotImplementedError


class MockAudioDeviceAdapter(AudioDeviceAdapter):
    """Deterministic, hardware-independent mock audio device adapter.

    Allows tests and local development to simulate:
    - Multiple mock microphones (built-in, USB headset, studio mic)
    - Permission granting, denial, and hardware unavailability
    - Selecting active input device
    - Spawning configured AudioSource instances
    """

    def __init__(
        self,
        initial_devices: Optional[List[DeviceInfo]] = None,
        initial_permission: PermissionState = PermissionState.GRANTED,
        auto_grant: bool = False,
    ):
        """Initialize mock device adapter.

        Args:
            initial_devices: Custom list of devices (defaults to 3 realistic mock devices).
            initial_permission: Initial PermissionState (default: GRANTED).
            auto_grant: Whether request_permission() automatically switches PROMPT -> GRANTED.
        """
        if initial_devices is not None:
            self._devices = list(initial_devices)
        else:
            self._devices = [
                DeviceInfo(
                    device_id="mock-default-mic",
                    name="Default Mock Microphone",
                    is_default=True,
                    sample_rates=[16000, 48000],
                    channels=1,
                    is_available=True,
                ),
                DeviceInfo(
                    device_id="mock-usb-headset",
                    name="USB Conference Headset",
                    is_default=False,
                    sample_rates=[16000, 44100, 48000],
                    channels=1,
                    is_available=True,
                ),
                DeviceInfo(
                    device_id="mock-studio-mic",
                    name="Pro Studio USB Microphone",
                    is_default=False,
                    sample_rates=[16000, 24000, 48000],
                    channels=2,
                    is_available=True,
                ),
            ]

        self._permission_state = initial_permission
        self._auto_grant = auto_grant

        # Pick default device if present and available, else first available
        self._selected_device_id: Optional[str] = None
        for dev in self._devices:
            if dev.is_default and dev.is_available:
                self._selected_device_id = dev.device_id
                break
        if self._selected_device_id is None and self._devices:
            for dev in self._devices:
                if dev.is_available:
                    self._selected_device_id = dev.device_id
                    break

    # --- Permission Controls ---

    def get_permission_state(self) -> PermissionState:
        """Return the current permission state."""
        return self._permission_state

    def set_permission_state(self, state: PermissionState) -> None:
        """Explicitly override permission state for test fixtures."""
        self._permission_state = state

    def request_permission(self) -> PermissionState:
        """Simulate requesting permission."""
        if self._permission_state == PermissionState.PROMPT:
            if self._auto_grant:
                self._permission_state = PermissionState.GRANTED
            # Otherwise remains PROMPT or test fixture can manipulate
        return self._permission_state

    # --- Device Discovery and Selection ---

    def list_devices(self) -> List[DeviceInfo]:
        """List available devices.

        Raises:
            DevicePermissionError: If permission is DENIED or UNAVAILABLE.
        """
        if self._permission_state == PermissionState.DENIED:
            raise DevicePermissionError(
                "Microphone access has been denied by the user or operating system.",
                code="AUDIO_PERMISSION_DENIED",
                details={"permission_state": self._permission_state.value},
            )
        if self._permission_state == PermissionState.UNAVAILABLE:
            raise DevicePermissionError(
                "Audio capture hardware is unavailable or disabled.",
                code="AUDIO_DEVICE_UNAVAILABLE",
                details={"permission_state": self._permission_state.value},
            )

        return [d for d in self._devices if d.is_available]

    def get_selected_device(self) -> DeviceInfo:
        """Get the currently selected input device."""
        if self._selected_device_id is None:
            raise DeviceNotFoundError("No audio device is currently selected.")

        for dev in self._devices:
            if dev.device_id == self._selected_device_id:
                if not dev.is_available:
                    raise DeviceNotFoundError(
                        f"Selected device '{dev.name}' ({dev.device_id}) is currently unavailable.",
                        details={"device_id": dev.device_id},
                    )
                return dev

        raise DeviceNotFoundError(
            f"Device ID '{self._selected_device_id}' not found.",
            details={"device_id": self._selected_device_id},
        )

    def select_device(self, device_id: str) -> DeviceInfo:
        """Select an input device by device_id."""
        if self._permission_state == PermissionState.DENIED:
            raise DevicePermissionError(
                "Cannot select device: microphone access is denied.",
                code="AUDIO_PERMISSION_DENIED",
                details={"device_id": device_id},
            )
        if self._permission_state == PermissionState.UNAVAILABLE:
            raise DevicePermissionError(
                "Cannot select device: audio capture subsystem is unavailable.",
                code="AUDIO_DEVICE_UNAVAILABLE",
                details={"device_id": device_id},
            )

        for dev in self._devices:
            if dev.device_id == device_id:
                if not dev.is_available:
                    raise DeviceNotFoundError(
                        f"Cannot select device '{dev.name}': device is unavailable.",
                        details={"device_id": device_id},
                    )
                self._selected_device_id = device_id
                return dev

        raise DeviceNotFoundError(
            f"No audio device found with ID '{device_id}'.",
            details={"device_id": device_id, "available_ids": [d.device_id for d in self._devices]},
        )

    # --- Device List Manipulation for Tests ---

    def add_device(self, device: DeviceInfo) -> None:
        """Add a device to the mock registry."""
        self._devices.append(device)

    def remove_device(self, device_id: str) -> None:
        """Remove a device from the mock registry."""
        self._devices = [d for d in self._devices if d.device_id != device_id]
        if self._selected_device_id == device_id:
            # Fall back to default or next available
            self._selected_device_id = None
            for dev in self._devices:
                if dev.is_default and dev.is_available:
                    self._selected_device_id = dev.device_id
                    break
            if self._selected_device_id is None:
                for dev in self._devices:
                    if dev.is_available:
                        self._selected_device_id = dev.device_id
                        break

    def set_device_availability(self, device_id: str, is_available: bool) -> None:
        """Simulate unplugging or disabling a device."""
        new_list = []
        for d in self._devices:
            if d.device_id == device_id:
                new_list.append(
                    DeviceInfo(
                        device_id=d.device_id,
                        name=d.name,
                        is_default=d.is_default,
                        sample_rates=d.sample_rates,
                        channels=d.channels,
                        is_available=is_available,
                    )
                )
            else:
                new_list.append(d)
        self._devices = new_list

    # --- Source Factory ---

    def create_source(
        self,
        config: Optional[AudioConfig] = None,
        pattern: str = "alternating",
        duration_seconds: Optional[float] = None,
        max_frames: Optional[int] = None,
        real_time: bool = False,
    ) -> AudioSource:
        """Create an AudioSource for the currently selected device."""
        if self._permission_state == PermissionState.DENIED:
            raise DevicePermissionError(
                "Cannot create audio source: microphone access is denied.",
                code="AUDIO_PERMISSION_DENIED",
            )
        if self._permission_state == PermissionState.UNAVAILABLE:
            raise DevicePermissionError(
                "Cannot create audio source: audio capture subsystem is unavailable.",
                code="AUDIO_DEVICE_UNAVAILABLE",
            )
        if self._permission_state == PermissionState.PROMPT:
            raise DevicePermissionError(
                "Cannot create audio source: microphone permission has not been requested/granted.",
                code="AUDIO_PERMISSION_PROMPT",
            )

        device = self.get_selected_device()
        used_config = config or AudioConfig()

        # Validate that requested config is supported by device
        if used_config.sample_rate not in device.sample_rates:
            raise AudioDeviceError(
                f"Selected device '{device.name}' does not support sample rate {used_config.sample_rate} Hz.",
                code="AUDIO_DEVICE_UNSUPPORTED_CONFIG",
                details={"supported_sample_rates": device.sample_rates, "requested": used_config.sample_rate},
            )
        if used_config.channels > device.channels:
            raise AudioDeviceError(
                f"Selected device '{device.name}' supports at most {device.channels} channel(s), got {used_config.channels}.",
                code="AUDIO_DEVICE_UNSUPPORTED_CONFIG",
                details={"max_channels": device.channels, "requested": used_config.channels},
            )

        return MockMicrophoneSource(
            config=used_config,
            pattern=pattern,
            duration_seconds=duration_seconds,
            max_frames=max_frames,
            real_time=real_time,
        )
