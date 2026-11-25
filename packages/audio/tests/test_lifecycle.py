"""
Unit tests for StreamLifecycleController (Week 2, Days 10-11).
Owner: Satwik A (feature/audio-vad)

Verifies:
- Explicit stream lifecycle states: IDLE, RUNNING, PAUSED, STOPPED, ERROR
- Every valid lifecycle transition:
  * IDLE -> RUNNING (start)
  * RUNNING -> PAUSED (pause)
  * PAUSED -> RUNNING (resume)
  * RUNNING -> STOPPED (stop)
  * PAUSED -> STOPPED (stop)
  * IDLE -> STOPPED (stop)
  * STOPPED -> RUNNING (restart)
- Rejection of invalid transitions with InvalidStateTransitionError:
  * start() when RUNNING or PAUSED
  * pause() when IDLE, PAUSED, STOPPED
  * resume() when IDLE, RUNNING, STOPPED
- Repeated start/stop and pause/resume scenarios
- Permission rejection at start() when DENIED, UNAVAILABLE, or PROMPT
- Safe cleanup of resources on stop(), failure, and context manager exit
- Frame reading behavior during RUNNING, PAUSED (counting dropped/skipped frames), and STOPPED
"""
import pytest

from packages.audio.device import (
    DeviceInfo,
    MockAudioDeviceAdapter,
    PermissionState,
)
from packages.audio.events import AudioEventDispatcher, AudioEventType
from packages.audio.exceptions import DevicePermissionError
from packages.audio.lifecycle import (
    InvalidStateTransitionError,
    StreamLifecycleController,
    StreamLifecycleError,
    StreamState,
)
from packages.audio.models import AudioConfig


def test_initial_lifecycle_state():
    """Verify newly instantiated controller begins in IDLE state."""
    adapter = MockAudioDeviceAdapter()
    controller = StreamLifecycleController(device_adapter=adapter)

    assert controller.state == StreamState.IDLE
    assert not controller.is_running
    assert not controller.is_paused
    assert controller.frames_produced == 0
    assert controller.frames_paused_dropped == 0
    # Reading frame when IDLE returns None
    assert controller.read_frame() is None


def test_valid_start_pause_resume_stop_transitions():
    """Verify full linear lifecycle: IDLE -> RUNNING -> PAUSED -> RUNNING -> STOPPED."""
    adapter = MockAudioDeviceAdapter()
    cfg = AudioConfig(sample_rate=16000, frame_duration_ms=20)
    controller = StreamLifecycleController(device_adapter=adapter, config=cfg)

    # 1. Start: IDLE -> RUNNING
    controller.start()
    assert controller.state == StreamState.RUNNING
    assert controller.is_running
    assert not controller.is_paused

    # Read a frame while running
    frame1 = controller.read_frame()
    assert frame1 is not None
    assert controller.frames_produced == 1

    # 2. Pause: RUNNING -> PAUSED
    controller.pause()
    assert controller.state == StreamState.PAUSED
    assert controller.is_paused
    assert not controller.is_running

    # Read frame while paused returns None and counts paused frames
    assert controller.read_frame() is None
    assert controller.frames_paused_dropped >= 1

    # 3. Resume: PAUSED -> RUNNING
    controller.resume()
    assert controller.state == StreamState.RUNNING
    assert controller.is_running

    frame2 = controller.read_frame()
    assert frame2 is not None
    assert controller.frames_produced >= 2

    # 4. Stop: RUNNING -> STOPPED
    controller.stop()
    assert controller.state == StreamState.STOPPED
    assert not controller.is_running
    assert controller.read_frame() is None

    # Idempotent stop
    controller.stop()
    assert controller.state == StreamState.STOPPED


def test_invalid_state_transitions():
    """Verify invalid state transitions are rejected with InvalidStateTransitionError."""
    adapter = MockAudioDeviceAdapter()
    controller = StreamLifecycleController(device_adapter=adapter)

    # In IDLE: cannot pause, resume
    with pytest.raises(InvalidStateTransitionError) as exc_p:
        controller.pause()
    assert exc_p.value.from_state == StreamState.IDLE
    assert exc_p.value.to_action == "pause"
    assert exc_p.value.code == "AUDIO_INVALID_STATE_TRANSITION"

    with pytest.raises(InvalidStateTransitionError):
        controller.resume()

    # Start -> RUNNING
    controller.start()

    # In RUNNING: cannot start again, cannot resume
    with pytest.raises(InvalidStateTransitionError):
        controller.start()
    with pytest.raises(InvalidStateTransitionError):
        controller.resume()

    # Pause -> PAUSED
    controller.pause()

    # In PAUSED: cannot start again, cannot pause again
    with pytest.raises(InvalidStateTransitionError):
        controller.start()
    with pytest.raises(InvalidStateTransitionError):
        controller.pause()

    # Stop -> STOPPED
    controller.stop()

    # In STOPPED: cannot pause, cannot resume
    with pytest.raises(InvalidStateTransitionError):
        controller.pause()
    with pytest.raises(InvalidStateTransitionError):
        controller.resume()


def test_repeated_start_stop_restarting():
    """Verify stream can be stopped and restarted cleanly multiple times."""
    adapter = MockAudioDeviceAdapter()
    controller = StreamLifecycleController(device_adapter=adapter)

    for i in range(3):
        controller.start()
        assert controller.state == StreamState.RUNNING
        frame = controller.read_frame()
        assert frame is not None
        controller.stop()
        assert controller.state == StreamState.STOPPED


def test_repeated_pause_resume_cycles():
    """Verify rapid pause and resume cycling."""
    adapter = MockAudioDeviceAdapter()
    controller = StreamLifecycleController(device_adapter=adapter)

    controller.start()
    for _ in range(5):
        controller.pause()
        assert controller.state == StreamState.PAUSED
        controller.resume()
        assert controller.state == StreamState.RUNNING

    controller.stop()


def test_start_permission_denied_transition_to_error():
    """Verify start() raises DevicePermissionError and enters ERROR state if permission is DENIED."""
    adapter = MockAudioDeviceAdapter(initial_permission=PermissionState.DENIED)
    controller = StreamLifecycleController(device_adapter=adapter)

    with pytest.raises(DevicePermissionError):
        controller.start()

    assert controller.state == StreamState.ERROR
    # Reading while in ERROR raises StreamLifecycleError
    with pytest.raises(StreamLifecycleError):
        controller.read_frame()

    # Stopping cleans up from ERROR to STOPPED
    controller.stop()
    assert controller.state == StreamState.STOPPED


def test_start_permission_unavailable_and_prompt():
    """Verify start() rejects UNAVAILABLE and PROMPT permissions."""
    adapter_unavail = MockAudioDeviceAdapter(initial_permission=PermissionState.UNAVAILABLE)
    controller1 = StreamLifecycleController(device_adapter=adapter_unavail)
    with pytest.raises(DevicePermissionError):
        controller1.start()
    assert controller1.state == StreamState.ERROR

    adapter_prompt = MockAudioDeviceAdapter(initial_permission=PermissionState.PROMPT, auto_grant=False)
    controller2 = StreamLifecycleController(device_adapter=adapter_prompt)
    with pytest.raises(DevicePermissionError):
        controller2.start()
    assert controller2.state == StreamState.ERROR


def test_stream_context_manager():
    """Verify context manager begins RUNNING and guarantees STOPPED on exit."""
    adapter = MockAudioDeviceAdapter()
    with StreamLifecycleController(device_adapter=adapter) as controller:
        assert controller.state == StreamState.RUNNING
        frame = controller.read_frame()
        assert frame is not None

    assert controller.state == StreamState.STOPPED


def test_generator_stream_and_pause():
    """Verify stream() generator yields frames and respects stopping."""
    adapter = MockAudioDeviceAdapter()
    # Create source producing 4 frames
    cfg = AudioConfig(sample_rate=16000, frame_duration_ms=20)
    controller = StreamLifecycleController(
        device_adapter=adapter,
        config=cfg,
        source_factory=lambda c: adapter.create_source(c, max_frames=4),
    )

    controller.start()
    frames = list(controller.stream())
    assert len(frames) == 4
    assert controller.state == StreamState.STOPPED


def test_source_factory_failure_handling():
    """Verify failure during source creation transitions safely to ERROR and cleans up."""
    adapter = MockAudioDeviceAdapter()

    def bad_factory(cfg):
        raise RuntimeError("Failed to open audio hardware pipe")

    controller = StreamLifecycleController(device_adapter=adapter, source_factory=bad_factory)
    with pytest.raises(RuntimeError):
        controller.start()

    assert controller.state == StreamState.ERROR
    controller.stop()
    assert controller.state == StreamState.STOPPED


def test_capture_state_mapping():
    """Verify capture_state property derives the UI-friendly status across all StreamStates."""
    adapter = MockAudioDeviceAdapter()
    controller = StreamLifecycleController(device_adapter=adapter)

    # 1. IDLE -> 'idle'
    assert controller.state == StreamState.IDLE
    assert controller.capture_state == "idle"

    # 2. RUNNING -> 'recording'
    controller.start()
    assert controller.state == StreamState.RUNNING
    assert controller.capture_state == "recording"

    # 3. PAUSED -> 'paused'
    controller.pause()
    assert controller.state == StreamState.PAUSED
    assert controller.capture_state == "paused"

    # 4. Resume to RUNNING -> 'recording'
    controller.resume()
    assert controller.capture_state == "recording"

    # 5. STOPPED -> 'idle'
    controller.stop()
    assert controller.state == StreamState.STOPPED
    assert controller.capture_state == "idle"

    # 6. DEVICE_LOST -> 'error'
    controller._state = StreamState.DEVICE_LOST
    assert controller.capture_state == "error"

    # 7. ERROR -> 'error'
    controller._state = StreamState.ERROR
    assert controller.capture_state == "error"


def test_stream_start_and_stop_events_dispatched():
    """Verify STREAM_START and STREAM_STOP events are emitted through event dispatcher."""
    adapter = MockAudioDeviceAdapter()
    dispatcher = AudioEventDispatcher()
    controller = StreamLifecycleController(
        device_adapter=adapter,
        event_dispatcher=dispatcher,
        session_id="sess-evt-test-001",
        correlation_id="corr-evt-test-001",
    )

    # 1. Start stream -> emits STREAM_START
    controller.start()
    start_events = dispatcher.get_events(AudioEventType.STREAM_START.value)
    assert len(start_events) == 1
    start_env = start_events[0]
    assert start_env.session_id == "sess-evt-test-001"
    assert start_env.correlation_id == "corr-evt-test-001"
    assert start_env.payload["state"] == "recording"
    assert start_env.payload["lifecycle_state"] == "RUNNING"

    # 2. Stop stream -> emits STREAM_STOP
    controller.stop()
    stop_events = dispatcher.get_events(AudioEventType.STREAM_STOP.value)
    assert len(stop_events) == 1
    stop_env = stop_events[0]
    assert stop_env.session_id == "sess-evt-test-001"
    assert stop_env.correlation_id == "corr-evt-test-001"
    assert stop_env.payload["state"] == "idle"
    assert stop_env.payload["lifecycle_state"] == "STOPPED"
    assert stop_env.payload["previous_state"] == "RUNNING"
    assert stop_env.payload["reason"] == "normal_stop"

