"""
Tests for Device-Loss Detection, Reconnection/Fallback, and Coordinated Cancellation (D17-18).
Owner: Satwik A (features/Satwik-week3) - Week 3 (Days 17-18)

Verifies:
1. Device disconnect during active stream (no crashes, clean transition to DEVICE_LOST).
2. Standardized device-loss event emission (audio.device.lost) with session_id and correlation_id.
3. Successful reconnection to original device when restored.
4. Fallback to another available device when original remains unavailable.
5. Recovery attempt when no device is available returns False cleanly.
6. Coordinated cancellation during active speech (clean speech_end + stream_cancelled).
7. Bounded buffer cleanup after cancellation (drained and closed).
8. Blocked consumer thread unblocked cleanly on cancellation.
9. Idempotency of repeated cancellation calls.
10. Device loss followed immediately by cancellation.
11. Zero audio frames emitted after cancellation.
12. Session and correlation ID preservation across loss, recovery, and frame production.
13. Pipeline interruption handling during speech on device loss.
14. Duplicate loss/recovery event suppression.
"""
from __future__ import annotations

import threading
import time
from typing import List

import pytest

from packages.audio.buffer import BackpressureStrategy, BoundedAudioBuffer
from packages.audio.device import DeviceInfo, MockAudioDeviceAdapter, PermissionState
from packages.audio.events import AudioEventDispatcher, AudioEventType, AudioSessionPipeline
from packages.audio.lifecycle import StreamLifecycleController, StreamState
from packages.audio.mock_mic import MockMicrophoneSource
from packages.audio.models import AudioConfig, AudioFrame, EventEnvelope
from packages.audio.vad import EnergyVAD


def _make_silence_frame(seq: int = 0) -> AudioFrame:
    return AudioFrame(
        data=b"\x00" * 640,
        frame_index=seq,
        sequence_number=seq,
        frame_duration_ms=20,
        sample_rate=16000,
        is_speech=False,
    )


def _make_speech_frame(seq: int = 0) -> AudioFrame:
    import math
    import struct
    sample_rate = 16000
    num_samples = int(sample_rate * 0.02)  # 20ms = 320 samples
    samples = [int(15000 * math.sin(2 * math.pi * 440 * i / sample_rate)) for i in range(num_samples)]
    raw = struct.pack(f"<{num_samples}h", *samples)
    return AudioFrame(
        data=raw,
        frame_index=seq,
        sequence_number=seq,
        frame_duration_ms=20,
        sample_rate=16000,
        is_speech=True,
    )


def _create_mock_adapter() -> MockAudioDeviceAdapter:
    """Create a mock device adapter with 3 distinct devices."""
    devices = [
        DeviceInfo(
            device_id="mic-primary",
            name="Primary Microphone",
            is_default=True,
            sample_rates=[16000],
            channels=1,
            is_available=True,
        ),
        DeviceInfo(
            device_id="mic-headset",
            name="USB Headset",
            is_default=False,
            sample_rates=[16000],
            channels=1,
            is_available=True,
        ),
        DeviceInfo(
            device_id="mic-backup",
            name="Backup Desk Mic",
            is_default=False,
            sample_rates=[16000],
            channels=1,
            is_available=True,
        ),
    ]
    return MockAudioDeviceAdapter(initial_devices=devices, initial_permission=PermissionState.GRANTED)


def test_device_disconnect_during_active_stream():
    """Verify device disconnect transitions state to DEVICE_LOST without throwing."""
    adapter = _create_mock_adapter()
    adapter.select_device("mic-primary")

    config = AudioConfig(sample_rate=16000, channels=1, frame_duration_ms=20)
    controller = StreamLifecycleController(device_adapter=adapter, config=config)

    controller.start()
    assert controller.state == StreamState.RUNNING
    assert controller.active_device_id == "mic-primary"

    # Read normal frame
    frame = controller.read_frame()
    assert frame is not None

    # Simulate hardware unplugging
    adapter.set_device_availability("mic-primary", False)

    # Next read detects loss and transitions gracefully to DEVICE_LOST
    lost_frame = controller.read_frame()
    assert lost_frame is None
    assert controller.state == StreamState.DEVICE_LOST
    assert controller.is_device_lost is True
    assert controller.is_running is False

    controller.stop()


def test_device_loss_event_emission_with_ids():
    """Verify audio.device.lost event is emitted with session_id and correlation_id."""
    adapter = _create_mock_adapter()
    adapter.select_device("mic-primary")

    dispatcher = AudioEventDispatcher()
    received_events: List[EventEnvelope] = []
    dispatcher.subscribe(lambda e: received_events.append(e))

    pipeline = AudioSessionPipeline(
        session_id="session-test-loss-1",
        correlation_id="corr-test-loss-1",
        dispatcher=dispatcher,
    )

    controller = StreamLifecycleController(
        device_adapter=adapter,
        session_id="session-test-loss-1",
        correlation_id="corr-test-loss-1",
        pipeline=pipeline,
    )

    controller.start()
    assert controller.active_device_id == "mic-primary"

    # Unplug device and read
    adapter.set_device_availability("mic-primary", False)
    controller.read_frame()

    assert controller.state == StreamState.DEVICE_LOST

    loss_events = [e for e in received_events if e.event_type == AudioEventType.DEVICE_LOST.value]
    assert len(loss_events) == 1
    loss_evt = loss_events[0]
    assert loss_evt.session_id == "session-test-loss-1"
    assert loss_evt.correlation_id == "corr-test-loss-1"
    assert loss_evt.payload["device_id"] == "mic-primary"
    assert loss_evt.payload["state"] == "DEVICE_LOST"


def test_successful_reconnection_to_original_device():
    """Verify restoring the original device allows reconnect() to resume RUNNING."""
    adapter = _create_mock_adapter()
    adapter.select_device("mic-primary")

    dispatcher = AudioEventDispatcher()
    events: List[EventEnvelope] = []
    dispatcher.subscribe(lambda e: events.append(e))

    pipeline = AudioSessionPipeline(
        session_id="session-recon-1",
        correlation_id="corr-recon-1",
        dispatcher=dispatcher,
    )

    controller = StreamLifecycleController(
        device_adapter=adapter,
        session_id="session-recon-1",
        correlation_id="corr-recon-1",
        pipeline=pipeline,
    )

    controller.start()
    # Read a frame
    f1 = controller.read_frame()
    assert f1 is not None

    # Unplug primary mic
    adapter.set_device_availability("mic-primary", False)
    controller.read_frame()
    assert controller.state == StreamState.DEVICE_LOST

    # Plug back in primary mic
    adapter.set_device_availability("mic-primary", True)

    # Reconnect
    success = controller.reconnect(target_device_id="mic-primary")
    assert success is True
    assert controller.state == StreamState.RUNNING
    assert controller.active_device_id == "mic-primary"

    # Verify recovery event
    recovered_events = [e for e in events if e.event_type == AudioEventType.DEVICE_RECOVERED.value]
    assert len(recovered_events) == 1
    rec_evt = recovered_events[0]
    assert rec_evt.payload["device_id"] == "mic-primary"
    assert rec_evt.payload["is_fallback"] is False
    assert rec_evt.session_id == "session-recon-1"
    assert rec_evt.correlation_id == "corr-recon-1"

    # Frame capture resumes
    f2 = controller.read_frame()
    assert f2 is not None

    controller.stop()


def test_reconnection_fallback_to_alternative_device():
    """Verify reconnect() falls back to another available device if original remains unavailable."""
    adapter = _create_mock_adapter()
    adapter.select_device("mic-primary")

    dispatcher = AudioEventDispatcher()
    events: List[EventEnvelope] = []
    dispatcher.subscribe(lambda e: events.append(e))

    controller = StreamLifecycleController(
        device_adapter=adapter,
        session_id="session-fallback-1",
        correlation_id="corr-fallback-1",
        event_dispatcher=dispatcher,
    )

    controller.start()
    adapter.set_device_availability("mic-primary", False)
    controller.read_frame()
    assert controller.state == StreamState.DEVICE_LOST

    # Reconnect with fallback allowed (mic-headset and mic-backup are available)
    success = controller.reconnect(allow_fallback=True)
    assert success is True
    assert controller.state == StreamState.RUNNING
    assert controller.active_device_id in ("mic-headset", "mic-backup")

    recovered_events = [e for e in events if e.event_type == AudioEventType.DEVICE_RECOVERED.value]
    assert len(recovered_events) == 1
    assert recovered_events[0].payload["is_fallback"] is True
    assert recovered_events[0].payload["device_id"] == controller.active_device_id

    controller.stop()


def test_reconnection_fails_cleanly_when_no_devices():
    """Verify reconnect() returns False safely when no devices are physically available."""
    adapter = _create_mock_adapter()
    adapter.select_device("mic-primary")

    controller = StreamLifecycleController(device_adapter=adapter)
    controller.start()

    # Unplug all devices
    for dev in adapter.list_devices():
        adapter.set_device_availability(dev.device_id, False)

    controller.read_frame()
    assert controller.state == StreamState.DEVICE_LOST

    # Attempt reconnect
    success = controller.reconnect(allow_fallback=True)
    assert success is False
    assert controller.state == StreamState.DEVICE_LOST

    controller.stop()


def test_cancellation_during_active_speech():
    """Verify cancel() during active speech cleanly emits speech_end before stream_cancelled."""
    adapter = _create_mock_adapter()
    dispatcher = AudioEventDispatcher()
    events: List[EventEnvelope] = []
    dispatcher.subscribe(lambda e: events.append(e))

    vad = EnergyVAD(threshold_db=-40.0, trigger_frames=1, hangover_frames=5)
    pipeline = AudioSessionPipeline(
        session_id="session-cancel-speech",
        correlation_id="corr-cancel-speech",
        vad=vad,
        dispatcher=dispatcher,
    )

    controller = StreamLifecycleController(
        device_adapter=adapter,
        session_id="session-cancel-speech",
        correlation_id="corr-cancel-speech",
        pipeline=pipeline,
    )

    controller.start()

    # Feed speech frame to enter speech state
    speech_frame = _make_speech_frame(seq=1)
    pipeline.process_frame(speech_frame)
    assert pipeline.in_speech is True

    # Cancel stream
    controller.cancel(reason="test_user_abort")

    assert controller.is_cancelled is True
    assert controller.state == StreamState.STOPPED
    assert pipeline.in_speech is False
    assert pipeline.is_cancelled is True

    event_types = [e.event_type for e in events]
    assert AudioEventType.SPEECH_START.value in event_types
    assert AudioEventType.SPEECH_END.value in event_types
    assert AudioEventType.STREAM_CANCELLED.value in event_types

    # Ensure speech_end preceded stream_cancelled
    speech_end_idx = event_types.index(AudioEventType.SPEECH_END.value)
    cancel_idx = event_types.index(AudioEventType.STREAM_CANCELLED.value)
    assert speech_end_idx < cancel_idx

    end_evt = events[speech_end_idx]
    assert end_evt.payload["reason"] == "cancellation"


def test_buffer_cleanup_after_cancellation():
    """Verify BoundedAudioBuffer is drained and closed after controller.cancel()."""
    adapter = _create_mock_adapter()
    buffer = BoundedAudioBuffer(max_frames=10, strategy=BackpressureStrategy.DROP_OLDEST)

    # Pre-fill buffer with 5 frames
    for i in range(5):
        frame = _make_silence_frame(seq=i)
        buffer.push(frame)
    assert len(buffer) == 5

    controller = StreamLifecycleController(
        device_adapter=adapter,
        buffer=buffer,
    )
    controller.start()

    controller.cancel(reason="buffer_test_cancel")
    assert buffer.is_closed is True
    assert len(buffer) == 0

    # Pushing into cancelled buffer raises BufferError
    with pytest.raises(Exception):
        buffer.push(_make_silence_frame(seq=99))


def test_blocked_consumer_unblocked_on_cancellation():
    """Verify a consumer thread blocked on buffer.pop() unblocks immediately on cancel()."""
    buffer = BoundedAudioBuffer(max_frames=10, strategy=BackpressureStrategy.BLOCK)
    controller = StreamLifecycleController(
        device_adapter=_create_mock_adapter(),
        buffer=buffer,
    )
    controller.start()

    consumer_result = {"frame": "unset", "finished": False}

    def consumer_thread():
        # Block waiting for frame
        frame = buffer.pop(timeout=3.0)
        consumer_result["frame"] = frame
        consumer_result["finished"] = True

    t = threading.Thread(target=consumer_thread, daemon=True)
    t.start()

    # Small delay to ensure thread is blocked on condition variable
    time.sleep(0.05)
    assert consumer_result["finished"] is False

    # Cancel controller
    controller.cancel()

    t.join(timeout=1.0)
    assert consumer_result["finished"] is True
    assert consumer_result["frame"] is None


def test_repeated_cancellation_idempotency():
    """Verify calling cancel() repeatedly is safe, idempotent, and produces exactly one cancel event."""
    dispatcher = AudioEventDispatcher()
    events: List[EventEnvelope] = []
    dispatcher.subscribe(lambda e: events.append(e))

    pipeline = AudioSessionPipeline(
        session_id="session-idemp",
        correlation_id="corr-idemp",
        dispatcher=dispatcher,
    )
    controller = StreamLifecycleController(
        device_adapter=_create_mock_adapter(),
        session_id="session-idemp",
        correlation_id="corr-idemp",
        pipeline=pipeline,
    )

    controller.start()

    controller.cancel(reason="cancel_1")
    controller.cancel(reason="cancel_2")
    controller.cancel(reason="cancel_3")

    cancel_events = [e for e in events if e.event_type == AudioEventType.STREAM_CANCELLED.value]
    assert len(cancel_events) == 1
    assert controller.state == StreamState.STOPPED
    assert controller.is_cancelled is True


def test_device_loss_followed_by_cancellation():
    """Verify handling device loss followed immediately by cancellation."""
    adapter = _create_mock_adapter()
    adapter.select_device("mic-primary")

    dispatcher = AudioEventDispatcher()
    events: List[EventEnvelope] = []
    dispatcher.subscribe(lambda e: events.append(e))

    controller = StreamLifecycleController(
        device_adapter=adapter,
        event_dispatcher=dispatcher,
    )
    controller.start()

    # Device lost
    adapter.set_device_availability("mic-primary", False)
    controller.read_frame()
    assert controller.state == StreamState.DEVICE_LOST

    # Cancelled while in DEVICE_LOST
    controller.cancel(reason="user_quit_after_loss")
    assert controller.state == StreamState.STOPPED
    assert controller.is_cancelled is True

    types = [e.event_type for e in events]
    assert AudioEventType.DEVICE_LOST.value in types
    assert AudioEventType.STREAM_CANCELLED.value in types


def test_zero_frames_emitted_after_cancellation():
    """Verify read_frame() returns None and generator terminates after cancel()."""
    adapter = _create_mock_adapter()
    controller = StreamLifecycleController(device_adapter=adapter)
    controller.start()

    f = controller.read_frame()
    assert f is not None

    controller.cancel()

    # Multiple subsequent reads must return None
    assert controller.read_frame() is None
    assert controller.read_frame() is None

    # Generator stream immediately terminates
    frames_from_gen = list(controller.stream())
    assert len(frames_from_gen) == 0


def test_session_and_correlation_ids_preserved_across_lifecycle():
    """Verify session_id and correlation_id remain constant through loss and recovery."""
    adapter = _create_mock_adapter()
    adapter.select_device("mic-primary")

    dispatcher = AudioEventDispatcher()
    events: List[EventEnvelope] = []
    dispatcher.subscribe(lambda e: events.append(e))

    sess_id = "session-audit-12345"
    corr_id = "corr-audit-67890"

    pipeline = AudioSessionPipeline(
        session_id=sess_id,
        correlation_id=corr_id,
        dispatcher=dispatcher,
    )
    controller = StreamLifecycleController(
        device_adapter=adapter,
        session_id=sess_id,
        correlation_id=corr_id,
        pipeline=pipeline,
    )

    controller.start()

    # Produce a frame
    f1 = controller.read_frame()
    assert f1 is not None
    pipeline.process_frame(f1)

    # Lose device
    adapter.set_device_availability("mic-primary", False)
    controller.read_frame()

    # Recover device
    adapter.set_device_availability("mic-primary", True)
    controller.reconnect(target_device_id="mic-primary")

    # Produce another frame
    f2 = controller.read_frame()
    assert f2 is not None
    pipeline.process_frame(f2)

    controller.cancel()

    # Verify all emitted events carry the exact same session_id and correlation_id
    assert len(events) >= 4
    for evt in events:
        assert evt.session_id == sess_id
        assert evt.correlation_id == corr_id


def test_pipeline_device_loss_interruption_during_speech():
    """Verify pipeline.handle_device_loss() terminates active speech cleanly."""
    dispatcher = AudioEventDispatcher()
    events: List[EventEnvelope] = []
    dispatcher.subscribe(lambda e: events.append(e))

    vad = EnergyVAD(threshold_db=-40.0, trigger_frames=1, hangover_frames=5)
    pipeline = AudioSessionPipeline(
        session_id="sess-loss-interr",
        correlation_id="corr-loss-interr",
        vad=vad,
        dispatcher=dispatcher,
    )

    # Ingest speech frame
    f = _make_speech_frame(seq=0)
    pipeline.process_frame(f)
    assert pipeline.in_speech is True

    # Trigger device loss on pipeline directly
    pipeline.handle_device_loss(device_id="mic-lost-1", reason="hardware_fault")

    assert pipeline.in_speech is False
    assert pipeline.is_device_lost is True

    # Events emitted: SPEECH_START, AUDIO_CHUNK, SPEECH_END, DEVICE_LOST
    types = [e.event_type for e in events]
    assert types == [
        AudioEventType.SPEECH_START.value,
        AudioEventType.AUDIO_CHUNK.value,
        AudioEventType.SPEECH_END.value,
        AudioEventType.DEVICE_LOST.value,
    ]

    end_evt = events[2]
    assert end_evt.payload["reason"] == "device_loss_interruption"
    loss_evt = events[3]
    assert loss_evt.payload["device_id"] == "mic-lost-1"


def test_duplicate_loss_and_recovery_events_suppression():
    """Verify duplicate handle_device_loss and handle_device_recovery calls are ignored."""
    dispatcher = AudioEventDispatcher()
    events: List[EventEnvelope] = []
    dispatcher.subscribe(lambda e: events.append(e))

    pipeline = AudioSessionPipeline(
        session_id="sess-dups",
        correlation_id="corr-dups",
        dispatcher=dispatcher,
    )

    # First loss succeeds
    loss1 = pipeline.handle_device_loss(device_id="mic-1")
    assert loss1 is not None

    # Second loss is suppressed
    loss2 = pipeline.handle_device_loss(device_id="mic-1")
    assert loss2 is None

    # First recovery succeeds
    rec1 = pipeline.handle_device_recovery(device_id="mic-1")
    assert rec1 is not None

    # Second recovery is suppressed
    rec2 = pipeline.handle_device_recovery(device_id="mic-1")
    assert rec2 is None

    assert len(events) == 2


def test_controller_direct_handle_device_loss():
    """Verify calling controller.handle_device_loss() transitions state and returns expected booleans."""
    adapter = _create_mock_adapter()
    controller = StreamLifecycleController(device_adapter=adapter)
    controller.start()

    assert controller.state == StreamState.RUNNING
    res1 = controller.handle_device_loss(reason="manual_signal")
    assert res1 is True
    assert controller.state == StreamState.DEVICE_LOST
    assert controller.is_device_lost is True

    # Calling again while already lost returns False
    res2 = controller.handle_device_loss(reason="redundant_signal")
    assert res2 is False

    controller.stop()


def test_controller_reconnect_invalid_states():
    """Verify reconnect() returns False when not in DEVICE_LOST or PAUSED, or when cancelled."""
    adapter = _create_mock_adapter()
    controller = StreamLifecycleController(device_adapter=adapter)

    # In IDLE
    assert controller.reconnect() is False

    controller.start()
    # In RUNNING
    assert controller.reconnect() is False

    controller.cancel()
    # In CANCELLED / STOPPED
    assert controller.reconnect() is False


def test_controller_stream_recovery_in_background():
    """Verify controller.stream() generator resumes yielding when reconnected from another thread."""
    adapter = _create_mock_adapter()
    adapter.select_device("mic-primary")

    controller = StreamLifecycleController(device_adapter=adapter)
    controller.start()

    yielded_frames: List[AudioFrame] = []

    def reader():
        for frame in controller.stream():
            yielded_frames.append(frame)
            if len(yielded_frames) >= 3:
                controller.stop()
                break

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    # Read 1 frame
    time.sleep(0.05)
    # Simulate device loss
    adapter.set_device_availability("mic-primary", False)
    controller.handle_device_loss(reason="bg_loss")

    time.sleep(0.05)
    # Restore device and reconnect
    adapter.set_device_availability("mic-primary", True)
    controller.reconnect(target_device_id="mic-primary")

    t.join(timeout=2.0)
    assert len(yielded_frames) >= 3
    controller.stop()


def test_pipeline_reset_and_properties():
    """Verify AudioSessionPipeline reset, total_frames_processed, and speech_segments_count properties."""
    dispatcher = AudioEventDispatcher()
    vad = EnergyVAD(threshold_db=-40.0, trigger_frames=1, hangover_frames=0)
    pipeline = AudioSessionPipeline(
        session_id="sess-prop-1",
        correlation_id="corr-prop-1",
        vad=vad,
        dispatcher=dispatcher,
    )

    assert pipeline.total_frames_processed == 0
    assert pipeline.speech_segments_count == 0
    assert pipeline.is_device_lost is False
    assert pipeline.is_cancelled is False

    f = _make_speech_frame(0)
    pipeline.process_frame(f)

    assert pipeline.total_frames_processed == 1
    assert pipeline.speech_segments_count == 1

    pipeline.reset()
    assert pipeline.total_frames_processed == 0
    assert pipeline.speech_segments_count == 0
    assert pipeline.in_speech is False
    assert len(pipeline.events) == 0


def test_dispatcher_unsubscribe_and_filter():
    """Verify AudioEventDispatcher unsubscribe and filtering by event_type."""
    dispatcher = AudioEventDispatcher()
    collected: List[EventEnvelope] = []

    def handler(evt: EventEnvelope):
        collected.append(evt)

    dispatcher.subscribe(handler, event_type=AudioEventType.DEVICE_LOST.value)

    env1 = EventEnvelope.create(
        event_type=AudioEventType.DEVICE_LOST.value,
        session_id="s1",
        correlation_id="c1",
        payload={"msg": "lost"},
    )
    env2 = EventEnvelope.create(
        event_type=AudioEventType.DEVICE_RECOVERED.value,
        session_id="s1",
        correlation_id="c1",
        payload={"msg": "rec"},
    )

    dispatcher.dispatch(env1)
    dispatcher.dispatch(env2)

    assert len(collected) == 1
    assert collected[0].event_type == AudioEventType.DEVICE_LOST.value

    # get_events filtering
    lost_events = dispatcher.get_events(AudioEventType.DEVICE_LOST.value)
    assert len(lost_events) == 1
    rec_events = dispatcher.get_events(AudioEventType.DEVICE_RECOVERED.value)
    assert len(rec_events) == 1

    # Unsubscribe
    unsub = dispatcher.unsubscribe(handler)
    assert unsub is True
    dispatcher.dispatch(env1)
    assert len(collected) == 1

    dispatcher.clear()
    assert len(dispatcher.history) == 0


def test_source_read_exception_triggers_device_loss():
    """Verify an exception raised by source.read_frame() transitions to DEVICE_LOST without crashing."""
    adapter = _create_mock_adapter()

    class FaultySource:
        def __init__(self, cfg):
            self.is_active = True

        def open(self):
            pass

        def close(self):
            self.is_active = False

        def read_frame(self):
            raise IOError("Simulated USB hardware I/O disconnect")

    controller = StreamLifecycleController(
        device_adapter=adapter,
        source_factory=lambda cfg: FaultySource(cfg),
    )
    controller.start()

    res = controller.read_frame()
    assert res is None
    assert controller.state == StreamState.DEVICE_LOST
    assert controller.is_device_lost is True


def test_permission_unavailable_and_prompt():
    """Verify PermissionState.UNAVAILABLE and PROMPT raise DevicePermissionError and set ERROR state."""
    from packages.audio.exceptions import DevicePermissionError

    adapter_unavail = MockAudioDeviceAdapter(initial_permission=PermissionState.UNAVAILABLE)
    ctrl_unavail = StreamLifecycleController(device_adapter=adapter_unavail)
    with pytest.raises(DevicePermissionError):
        ctrl_unavail.start()
    assert ctrl_unavail.state == StreamState.ERROR

    adapter_prompt = MockAudioDeviceAdapter(initial_permission=PermissionState.PROMPT)
    ctrl_prompt = StreamLifecycleController(device_adapter=adapter_prompt)
    with pytest.raises(DevicePermissionError):
        ctrl_prompt.start()
    assert ctrl_prompt.state == StreamState.ERROR


def test_paused_stream_read_frame_behavior():
    """Verify read_frame() while PAUSED drops frames, stops on EOF, or catches errors."""
    adapter = _create_mock_adapter()
    controller = StreamLifecycleController(device_adapter=adapter)
    controller.start()

    controller.pause()
    assert controller.state == StreamState.PAUSED
    res = controller.read_frame()
    assert res is None
    assert controller.frames_paused_dropped == 1

    controller.stop()


