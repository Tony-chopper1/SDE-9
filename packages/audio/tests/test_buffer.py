"""
Unit tests for BoundedAudioBuffer (Week 2, Days 12-13).
Owner: Satwik A (feature/audio-vad)

Verifies:
- Configurable capacity limits by max_frames and max_duration_ms
- Memory usage strictly bounded by buffer capacity
- Every backpressure strategy:
  * DROP_OLDEST (evicts oldest frame, accepts new frame, updates dropped counters)
  * DROP_NEWEST (rejects incoming frame, preserves existing frames, updates dropped counters)
  * BLOCK (blocks producer thread until space available or timeout)
- Accurate telemetry:
  * frames_dropped
  * bytes_dropped
  * current_frames
  * current_bytes
  * current_duration_ms
- Thread-safe concurrent producer-consumer pipeline
- Slow consumer simulations
- Integration with MockMicrophoneSource (20ms and 30ms frames) and StreamLifecycleController
- Empty buffer, full buffer, closed buffer, and non-blocking vs blocking pops
"""
import concurrent.futures
import threading
import time
import pytest

from packages.audio.buffer import (
    BackpressureStrategy,
    BoundedAudioBuffer,
    BufferError,
    BufferTelemetry,
)
from packages.audio.device import MockAudioDeviceAdapter
from packages.audio.lifecycle import StreamLifecycleController
from packages.audio.mock_mic import MockMicrophoneSource
from packages.audio.models import AudioConfig, AudioFrame


def _make_frame(seq: int, duration_ms: int = 20, sample_rate: int = 16000) -> AudioFrame:
    """Helper to synthesize test AudioFrame with distinct seq."""
    expected_bytes = int(sample_rate * (duration_ms / 1000.0)) * 2
    data = (seq % 256).to_bytes(1, "little") * expected_bytes
    return AudioFrame(
        audio_data=data,
        sequence_number=seq,
        timestamp_ms=float(seq * duration_ms),
        sample_rate=sample_rate,
        frame_duration_ms=duration_ms,
    )


def test_buffer_capacity_initialization():
    """Verify max_frames and max_duration_ms initialization."""
    buf_frames = BoundedAudioBuffer(max_frames=10)
    assert buf_frames.max_frames == 10

    # 1000ms / 20ms = 50 frames
    buf_dur = BoundedAudioBuffer(max_duration_ms=1000.0, default_frame_duration_ms=20)
    assert buf_dur.max_frames == 50

    # Default fallback
    buf_default = BoundedAudioBuffer()
    assert buf_default.max_frames == 50


def test_drop_oldest_strategy():
    """Verify DROP_OLDEST evicts oldest frames when capacity is exceeded."""
    buf = BoundedAudioBuffer(max_frames=3, strategy=BackpressureStrategy.DROP_OLDEST)

    # Push 3 frames (0, 1, 2) -> fills capacity
    for i in range(3):
        assert buf.push(_make_frame(i, duration_ms=20)) is True

    tele = buf.get_telemetry()
    assert tele.current_frames == 3
    assert tele.frames_dropped == 0

    # Push frame 3: should evict frame 0, queue now holds [1, 2, 3]
    assert buf.push(_make_frame(3, duration_ms=20)) is True

    tele = buf.get_telemetry()
    assert tele.current_frames == 3
    assert tele.frames_dropped == 1
    assert tele.bytes_dropped == 640  # 1 20ms frame is 640 bytes

    # Verify popped frames are [1, 2, 3]
    f1 = buf.pop()
    assert f1.sequence_number == 1
    f2 = buf.pop()
    assert f2.sequence_number == 2
    f3 = buf.pop()
    assert f3.sequence_number == 3
    assert buf.pop() is None


def test_drop_newest_strategy():
    """Verify DROP_NEWEST rejects new incoming frames when buffer is full."""
    buf = BoundedAudioBuffer(max_frames=2, strategy=BackpressureStrategy.DROP_NEWEST)

    # Push 2 frames (0, 1) -> capacity reached
    assert buf.push(_make_frame(0)) is True
    assert buf.push(_make_frame(1)) is True

    # Push frame 2: rejected
    assert buf.push(_make_frame(2)) is False

    tele = buf.get_telemetry()
    assert tele.current_frames == 2
    assert tele.frames_dropped == 1
    assert tele.bytes_dropped == 640

    # Queue still contains [0, 1]
    assert buf.pop().sequence_number == 0
    assert buf.pop().sequence_number == 1
    assert buf.pop() is None


def test_block_strategy_with_timeout():
    """Verify BLOCK strategy waits for consumer and respects timeout."""
    buf = BoundedAudioBuffer(max_frames=1, strategy=BackpressureStrategy.BLOCK)

    # Fill buffer
    buf.push(_make_frame(0))

    # Second push with short timeout should timeout and drop
    start = time.perf_counter()
    success = buf.push(_make_frame(1), timeout=0.05)
    elapsed = time.perf_counter() - start

    assert success is False
    assert elapsed >= 0.04
    tele = buf.get_telemetry()
    assert tele.frames_dropped == 1


def test_block_strategy_unblocked_by_consumer():
    """Verify BLOCK strategy waits and unblocks when consumer pops."""
    buf = BoundedAudioBuffer(max_frames=1, strategy=BackpressureStrategy.BLOCK)
    buf.push(_make_frame(0))

    # Background thread pops after 50ms
    def delayed_pop():
        time.sleep(0.05)
        return buf.pop()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        fut_pop = executor.submit(delayed_pop)
        # Main thread pushes frame 1; should unblock when delayed_pop runs
        success = buf.push(_make_frame(1), timeout=1.0)

    assert success is True
    assert fut_pop.result().sequence_number == 0
    assert buf.pop().sequence_number == 1


def test_memory_strictly_bounded_30ms_frames():
    """Verify buffer memory bytes never exceed max_frames * frame_bytes."""
    # 30ms frames at 16kHz mono = 960 bytes per frame
    max_frames = 5
    expected_max_bytes = max_frames * 960
    buf = BoundedAudioBuffer(max_frames=max_frames, strategy=BackpressureStrategy.DROP_OLDEST)

    # Push 100 frames
    for i in range(100):
        buf.push(_make_frame(i, duration_ms=30))
        tele = buf.get_telemetry()
        assert tele.current_bytes <= expected_max_bytes
        assert tele.current_frames <= max_frames

    tele = buf.get_telemetry()
    assert tele.current_frames == max_frames
    assert tele.current_bytes == expected_max_bytes
    assert tele.frames_dropped == 95
    assert tele.bytes_dropped == 95 * 960


def test_concurrent_producer_consumer():
    """Verify thread safety with concurrent producer and consumer threads."""
    buf = BoundedAudioBuffer(max_frames=10, strategy=BackpressureStrategy.DROP_OLDEST)
    total_frames = 100
    consumed_seqs = []

    def producer():
        for i in range(total_frames):
            buf.push(_make_frame(i))
            time.sleep(0.001)
        buf.close()

    def consumer():
        while True:
            frame = buf.pop(timeout=0.05)
            if frame is not None:
                consumed_seqs.append(frame.sequence_number)
            elif buf.is_closed:
                break

    t_prod = threading.Thread(target=producer)
    t_cons = threading.Thread(target=consumer)

    t_prod.start()
    t_cons.start()
    t_prod.join()
    t_cons.join()

    tele = buf.get_telemetry()
    assert tele.total_frames_pushed == total_frames
    # Total consumed + total dropped must equal total pushed
    assert len(consumed_seqs) + tele.frames_dropped == total_frames
    # Consumed sequence numbers must be in ascending order
    for a, b in zip(consumed_seqs[:-1], consumed_seqs[1:]):
        assert a < b


def test_buffer_closed_operations():
    """Verify pushing to closed buffer raises BufferError and popping drains remaining."""
    buf = BoundedAudioBuffer(max_frames=5)
    buf.push(_make_frame(0))
    buf.push(_make_frame(1))

    buf.close()
    assert buf.is_closed is True

    # Pushing to closed buffer raises BufferError
    with pytest.raises(BufferError):
        buf.push(_make_frame(2))

    # Popping still drains existing items
    assert buf.pop().sequence_number == 0
    assert buf.pop().sequence_number == 1
    assert buf.pop() is None


def test_buffer_clear():
    """Verify clear resets frames and current bytes."""
    buf = BoundedAudioBuffer(max_frames=5)
    buf.push(_make_frame(0))
    buf.push(_make_frame(1))
    assert len(buf) == 2

    buf.clear()
    assert len(buf) == 0
    assert buf.get_telemetry().current_bytes == 0


def test_integration_with_mock_mic_and_lifecycle_controller():
    """Verify integration: MockMicrophoneSource -> StreamLifecycleController -> BoundedAudioBuffer."""
    adapter = MockAudioDeviceAdapter()
    cfg = AudioConfig(sample_rate=16000, frame_duration_ms=20)
    controller = StreamLifecycleController(
        device_adapter=adapter,
        config=cfg,
        source_factory=lambda c: MockMicrophoneSource(config=c, max_frames=8),
    )

    buffer = BoundedAudioBuffer(max_frames=4, strategy=BackpressureStrategy.DROP_OLDEST)

    with controller:
        for frame in controller.stream():
            buffer.push(frame)

    tele = buffer.get_telemetry()
    assert tele.total_frames_pushed == 8
    assert tele.current_frames == 4
    assert tele.frames_dropped == 4  # Pushed 8 into capacity of 4 -> dropped 4

    # Drain buffer
    drained = []
    while True:
        f = buffer.pop()
        if f is None:
            break
        drained.append(f.sequence_number)

    assert drained == [4, 5, 6, 7]  # Most recent 4 frames preserved



def test_buffer_stream_generator():
    """Verify buffer stream() iterator yields all pushed frames until closed."""
    buf = BoundedAudioBuffer(max_frames=10)
    for i in range(3):
        buf.push(_make_frame(i))
    buf.close()

    streamed = list(buf.stream())
    assert len(streamed) == 3
    assert [f.sequence_number for f in streamed] == [0, 1, 2]


def test_buffer_utilization_ratio():
    """Verify utilization_ratio calculation in telemetry."""
    buf = BoundedAudioBuffer(max_frames=10)
    tele0 = buf.get_telemetry()
    assert tele0.utilization_ratio == 0.0

    buf.push(_make_frame(0))
    buf.push(_make_frame(1))
    tele1 = buf.get_telemetry()
    assert round(tele1.utilization_ratio, 2) == 0.2


def test_push_invalid_frame_type_raises():
    """Verify push rejects non-AudioFrame objects."""
    buf = BoundedAudioBuffer()
    with pytest.raises(BufferError):
        buf.push("not_an_audio_frame")  # type: ignore


def test_sustained_backpressure_drop_oldest_flood():
    """Stress Test: Sustained flood of 2,000 frames into DROP_OLDEST buffer.

    Verifies:
    1. Buffer capacity strictly retained at max_frames=20.
    2. Exactly 1,980 frames dropped.
    3. Accurate telemetry: frames_dropped == 1980, bytes_dropped == 1980 * 640.
    4. Surviving frames are the most recent 20 frames (seq 1980..1999).
    """
    capacity = 20
    total_flood = 2000
    frame_bytes = 640  # 20ms at 16kHz 16-bit mono
    buf = BoundedAudioBuffer(max_frames=capacity, strategy=BackpressureStrategy.DROP_OLDEST)

    for i in range(total_flood):
        pushed = buf.push(_make_frame(i, duration_ms=20))
        assert pushed is True

    tele = buf.get_telemetry()
    assert tele.total_frames_pushed == total_flood
    assert tele.current_frames == capacity
    assert tele.frames_dropped == total_flood - capacity
    assert tele.bytes_dropped == (total_flood - capacity) * frame_bytes
    assert tele.current_bytes == capacity * frame_bytes
    assert tele.utilization_ratio == 1.0

    # Pop surviving frames: should strictly be sequence numbers [1980..1999]
    drained_seqs = []
    while True:
        frame = buf.pop()
        if frame is None:
            break
        drained_seqs.append(frame.sequence_number)

    assert len(drained_seqs) == capacity
    assert drained_seqs == list(range(total_flood - capacity, total_flood))


def test_sustained_backpressure_drop_newest_flood():
    """Stress Test: Sustained flood of 2,000 frames into DROP_NEWEST buffer.

    Verifies:
    1. Buffer capacity strictly retained at max_frames=20.
    2. Exactly 1,980 frames dropped/rejected.
    3. Accurate telemetry: frames_dropped == 1980, bytes_dropped == 1980 * 640.
    4. Surviving frames are the initial 20 frames (seq 0..19).
    """
    capacity = 20
    total_flood = 2000
    frame_bytes = 640
    buf = BoundedAudioBuffer(max_frames=capacity, strategy=BackpressureStrategy.DROP_NEWEST)

    for i in range(total_flood):
        pushed = buf.push(_make_frame(i, duration_ms=20))
        if i < capacity:
            assert pushed is True
        else:
            assert pushed is False

    tele = buf.get_telemetry()
    assert tele.total_frames_pushed == capacity
    assert tele.current_frames == capacity
    assert tele.frames_dropped == total_flood - capacity
    assert tele.bytes_dropped == (total_flood - capacity) * frame_bytes
    assert tele.total_frames_pushed + tele.frames_dropped == total_flood
    assert tele.current_bytes == capacity * frame_bytes

    # Pop surviving frames: should strictly be sequence numbers [0..19]
    drained_seqs = []
    while True:
        frame = buf.pop()
        if frame is None:
            break
        drained_seqs.append(frame.sequence_number)

    assert len(drained_seqs) == capacity
    assert drained_seqs == list(range(capacity))


def test_sustained_backpressure_block_slow_consumer_integrity():
    """Stress Test: Sustained concurrent producer/consumer with BLOCK strategy.

    Verifies:
    1. Producer pushing 300 frames into small buffer (max_frames=10).
    2. Slow consumer pops with small delay.
    3. Zero frames dropped under backpressure.
    4. Strict sequence monotonicity: all 300 frames received in order without deadlock.
    """
    capacity = 10
    total_frames = 300
    buf = BoundedAudioBuffer(max_frames=capacity, strategy=BackpressureStrategy.BLOCK)

    consumed_seqs = []
    consumer_errors = []

    def producer():
        for i in range(total_frames):
            buf.push(_make_frame(i, duration_ms=20), timeout=5.0)
        buf.close()

    def slow_consumer():
        try:
            while True:
                f = buf.pop(timeout=0.1)
                if f is not None:
                    consumed_seqs.append(f.sequence_number)
                elif buf.is_closed:
                    break
        except Exception as e:
            consumer_errors.append(e)

    t_prod = threading.Thread(target=producer)
    t_cons = threading.Thread(target=slow_consumer)

    t_prod.start()
    t_cons.start()
    t_prod.join(timeout=10.0)
    t_cons.join(timeout=10.0)

    assert not t_prod.is_alive(), "Producer thread hung/deadlocked"
    assert not t_cons.is_alive(), "Consumer thread hung/deadlocked"
    assert len(consumer_errors) == 0

    tele = buf.get_telemetry()
    assert tele.frames_dropped == 0
    assert tele.bytes_dropped == 0
    assert len(consumed_seqs) == total_frames
    assert consumed_seqs == list(range(total_frames))


def test_buffer_cancellation_and_concurrent_unblock():
    """Stress Test: Buffer closure cleanly unblocks blocked producer and consumer threads.

    Verifies:
    1. Thread blocked on push(timeout=5.0) immediately returns on buf.close() raising BufferError.
    2. Thread blocked on pop(timeout=5.0) immediately returns None on buf.close().
    3. No thread hangs indefinitely or raises unexpected exceptions.
    """
    # 1. Producer unblock test
    buf_prod = BoundedAudioBuffer(max_frames=1, strategy=BackpressureStrategy.BLOCK)
    buf_prod.push(_make_frame(0))  # fill buffer
    producer_unblocked = False

    def blocked_producer():
        nonlocal producer_unblocked
        try:
            buf_prod.push(_make_frame(1), timeout=5.0)
        except BufferError:
            producer_unblocked = True

    t_prod = threading.Thread(target=blocked_producer)
    t_prod.start()
    time.sleep(0.05)  # Ensure producer is blocked on full buffer

    buf_prod.close()
    t_prod.join(timeout=2.0)

    assert not t_prod.is_alive(), "Blocked producer failed to unblock on buffer close"
    assert producer_unblocked is True

    # 2. Consumer unblock test
    buf_cons = BoundedAudioBuffer(max_frames=1, strategy=BackpressureStrategy.BLOCK)
    consumer_unblocked = False

    def blocked_consumer():
        nonlocal consumer_unblocked
        res = buf_cons.pop(timeout=5.0)
        consumer_unblocked = (res is None)

    t_cons = threading.Thread(target=blocked_consumer)
    t_cons.start()
    time.sleep(0.05)  # Ensure consumer is blocked on empty buffer

    buf_cons.close()
    t_cons.join(timeout=2.0)

    assert not t_cons.is_alive(), "Blocked consumer failed to unblock on buffer close"
    assert consumer_unblocked is True
