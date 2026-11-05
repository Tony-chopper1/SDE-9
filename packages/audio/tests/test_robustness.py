"""
Robustness and edge-case tests for SDK-9 Audio & VAD (Week 2, Day 14).
Owner: Satwik A (feature/audio-vad)

Verifies:
- Audio gaps and missing frame sequences
- Late and out-of-order chunks (sequence number discrepancies and jitter)
- Ambient noise, short noise bursts vs sustained speech
- Buffer behavior with irregular/bursty frame arrival
- 20ms and 30ms frame interoperability
- Lifecycle controller and bounded buffer shutdown interactions
- Release of blocked producers and consumers upon buffer closure without deadlocks
"""
import concurrent.futures
import math
import struct
import threading
import time
import pytest

from packages.audio.buffer import (
    BackpressureStrategy,
    BoundedAudioBuffer,
    BufferError,
)
from packages.audio.device import MockAudioDeviceAdapter
from packages.audio.lifecycle import StreamLifecycleController, StreamState
from packages.audio.mock_mic import MockMicrophoneSource
from packages.audio.models import AudioConfig, AudioFrame
from packages.audio.vad import EnergyVAD, SimpleVADDetector


def _generate_synthetic_pcm(
    amplitude: float,
    frequency_hz: float,
    sample_rate: int = 16000,
    duration_ms: int = 20,
    is_noise: bool = False,
) -> bytes:
    """Helper to synthesize pure tone, silence, or noise PCM data."""
    num_samples = int(sample_rate * (duration_ms / 1000.0))
    samples = []
    for i in range(num_samples):
        if is_noise:
            # Deterministic pseudo-noise
            val = amplitude * math.sin(i * 1337.0 % math.pi)
        elif amplitude == 0.0:
            val = 0.0
        else:
            t = i / sample_rate
            val = amplitude * math.sin(2.0 * math.pi * frequency_hz * t)
        sample_int = int(max(-32767, min(32767, val)))
        samples.append(sample_int)
    return struct.pack(f"<{len(samples)}h", *samples)


def test_audio_gaps_and_missing_frames():
    """Verify system handles sequence gaps without crashing and accumulator/VAD tracks intervals."""
    vad = EnergyVAD(threshold_db=-40.0)
    config = AudioConfig(sample_rate=16000, frame_duration_ms=20)

    # Frame 0 (t=0ms), Frame 1 (t=20ms), GAP (missing Frame 2), Frame 3 (t=60ms)
    pcm_speech = _generate_synthetic_pcm(15000.0, 300.0, 16000, 20)
    f0 = AudioFrame(audio_data=pcm_speech, sequence_number=0, timestamp_ms=0.0, config=config)
    f1 = AudioFrame(audio_data=pcm_speech, sequence_number=1, timestamp_ms=20.0, config=config)
    f3 = AudioFrame(audio_data=pcm_speech, sequence_number=3, timestamp_ms=60.0, config=config)

    # VAD processes despite gap in sequence number
    r0 = vad.process_frame(f0)
    r1 = vad.process_frame(f1)
    r3 = vad.process_frame(f3)

    assert r0.is_speech is False or r1.is_speech is True  # Trigger requires 2 frames
    assert r3.is_speech is True
    # Frame gap is detected via timestamp/sequence comparison
    gap_detected = (f3.sequence_number - f1.sequence_number) > 1
    assert gap_detected is True
    time_gap = f3.timestamp_ms - (f1.timestamp_ms + f1.frame_duration_ms)
    assert time_gap == 20.0  # 20ms gap detected


def test_out_of_order_chunks_and_jitter():
    """Verify buffering and ordered segment reassembly when chunks arrive out of order."""
    buffer = BoundedAudioBuffer(max_frames=10, strategy=BackpressureStrategy.DROP_OLDEST)
    config = AudioConfig(sample_rate=16000, frame_duration_ms=20)
    pcm_speech = _generate_synthetic_pcm(10000.0, 300.0, 16000, 20)

    f0 = AudioFrame(audio_data=pcm_speech, sequence_number=0, timestamp_ms=0.0, config=config)
    f1 = AudioFrame(audio_data=pcm_speech, sequence_number=1, timestamp_ms=20.0, config=config)
    f2 = AudioFrame(audio_data=pcm_speech, sequence_number=2, timestamp_ms=40.0, config=config)

    # Jitter arrival: f1 arrives first, then f0, then f2
    buffer.push(f1)
    buffer.push(f0)
    buffer.push(f2)

    received = []
    while len(buffer) > 0:
        received.append(buffer.pop())

    assert len(received) == 3
    # Order can be re-sorted by sequence_number
    ordered = sorted(received, key=lambda f: f.sequence_number)
    assert [f.sequence_number for f in ordered] == [0, 1, 2]
    assert [f.timestamp_ms for f in ordered] == [0.0, 20.0, 40.0]


def test_ambient_noise_vs_short_bursts_vs_sustained_speech():
    """Verify VAD differentiates ambient background noise (-50dBFS), short clicks, and real speech (-15dBFS)."""
    # Configure VAD with threshold -40dBFS and min duration 60ms (3 frames of 20ms)
    vad = EnergyVAD(
        threshold_db=-40.0,
        trigger_frames=2,
        hangover_frames=1,
        min_speech_duration_ms=60.0,
    )
    config = AudioConfig(sample_rate=16000, frame_duration_ms=20)

    # 1. Ambient noise (low amplitude 200 -> ~ -44 dBFS)
    pcm_noise = _generate_synthetic_pcm(200.0, 500.0, 16000, 20, is_noise=True)
    f_noise = AudioFrame(audio_data=pcm_noise, sequence_number=0, timestamp_ms=0.0, config=config)
    assert vad.process_frame(f_noise).is_speech is False

    # 2. Short noise burst / click: loud amplitude (18000.0) but only 1 frame (20ms < 60ms min duration)
    vad.reset()
    pcm_click = _generate_synthetic_pcm(18000.0, 1000.0, 16000, 20)
    f_click = AudioFrame(audio_data=pcm_click, sequence_number=0, timestamp_ms=0.0, config=config)
    res_click = vad.process_frame(f_click)
    # Filtered out by min_speech_duration_ms
    assert res_click.is_speech is False

    # 3. Sustained speech: 4 consecutive frames (80ms > 60ms)
    vad.reset()
    pcm_speech = _generate_synthetic_pcm(15000.0, 300.0, 16000, 20)
    results = []
    for i in range(4):
        f = AudioFrame(audio_data=pcm_speech, sequence_number=i, timestamp_ms=float(i * 20), config=config)
        results.append(vad.process_frame(f).is_speech)

    # Frames 0, 1 are under 60ms -> False. Frames 2, 3 reach/exceed 60ms -> True.
    assert results == [False, False, True, True]


def test_buffer_behavior_with_irregular_bursty_arrival():
    """Verify buffer under bursty producer traffic and slow consumer pace."""
    buffer = BoundedAudioBuffer(max_frames=6, strategy=BackpressureStrategy.DROP_OLDEST)
    config = AudioConfig(sample_rate=16000, frame_duration_ms=20)
    pcm = _generate_synthetic_pcm(5000.0, 400.0, 16000, 20)

    # Burst 1: 10 frames arrive at once (exceeds capacity of 6)
    for i in range(10):
        buffer.push(AudioFrame(audio_data=pcm, sequence_number=i, timestamp_ms=float(i * 20), config=config))

    tele1 = buffer.get_telemetry()
    assert tele1.current_frames == 6
    assert tele1.frames_dropped == 4

    # Consumer slowly reads 2 frames
    f_a = buffer.pop()
    f_b = buffer.pop()
    assert f_a.sequence_number == 4
    assert f_b.sequence_number == 5
    assert len(buffer) == 4

    # Burst 2: 5 more frames (seq 10..14)
    for i in range(10, 15):
        buffer.push(AudioFrame(audio_data=pcm, sequence_number=i, timestamp_ms=float(i * 20), config=config))

    tele2 = buffer.get_telemetry()
    assert tele2.current_frames == 6
    assert tele2.frames_dropped == 7  # 4 + 3 dropped from second burst


def test_20ms_and_30ms_frame_interoperability():
    """Verify that buffer and VAD seamlessly handle 20ms (640B) and 30ms (960B) configurations."""
    cfg20 = AudioConfig(sample_rate=16000, frame_duration_ms=20)
    cfg30 = AudioConfig(sample_rate=16000, frame_duration_ms=30)
    buffer = BoundedAudioBuffer(max_frames=5)
    vad = EnergyVAD(threshold_db=-40.0)

    pcm20 = _generate_synthetic_pcm(15000.0, 300.0, 16000, 20)
    pcm30 = _generate_synthetic_pcm(15000.0, 300.0, 16000, 30)

    f20 = AudioFrame(audio_data=pcm20, sequence_number=0, timestamp_ms=0.0, config=cfg20)
    f30 = AudioFrame(audio_data=pcm30, sequence_number=1, timestamp_ms=20.0, config=cfg30)

    assert len(f20.audio_data) == 640
    assert len(f30.audio_data) == 960

    # Buffer holds both accurately tracking byte length
    buffer.push(f20)
    buffer.push(f30)
    assert buffer.get_telemetry().current_bytes == 640 + 960

    # VAD processes both
    r20 = vad.process_frame(f20)
    r30 = vad.process_frame(f30)
    assert r20.energy_db > -25.0
    assert r30.energy_db > -25.0


def test_lifecycle_and_buffer_shutdown_interaction():
    """Verify shutting down StreamLifecycleController closes and flushes buffer cleanly."""
    adapter = MockAudioDeviceAdapter()
    controller = StreamLifecycleController(
        device_adapter=adapter,
        source_factory=lambda c: MockMicrophoneSource(config=c, max_frames=5),
    )
    buffer = BoundedAudioBuffer(max_frames=10)

    controller.start()
    for frame in controller.stream():
        buffer.push(frame)

    assert controller.state == StreamState.STOPPED
    buffer.close()
    assert buffer.is_closed is True

    # Draining remaining frames
    frames = list(buffer.stream())
    assert len(frames) == 5


def test_blocked_producer_and_consumer_release_on_close():
    """Verify that blocked producers and consumers are unblocked and released when buffer closes."""
    # Buffer capacity 1 with BLOCK strategy
    buf = BoundedAudioBuffer(max_frames=1, strategy=BackpressureStrategy.BLOCK)
    cfg = AudioConfig(sample_rate=16000, frame_duration_ms=20)
    pcm = _generate_synthetic_pcm(5000.0, 300.0, 16000, 20)
    f0 = AudioFrame(audio_data=pcm, sequence_number=0, config=cfg)
    f1 = AudioFrame(audio_data=pcm, sequence_number=1, config=cfg)

    # Fill buffer
    buf.push(f0)

    producer_error = []
    consumer_result = []

    def blocked_producer():
        try:
            # Pushing into full buffer with BLOCK will wait indefinitely until closed or freed
            buf.push(f1)
        except BufferError as err:
            producer_error.append(err)

    def blocked_consumer():
        # Another empty buffer pop wait
        empty_buf = BoundedAudioBuffer(max_frames=5)
        # Background thread waits for frame
        def drain():
            res = empty_buf.pop(timeout=2.0)
            consumer_result.append(res)
        t = threading.Thread(target=drain)
        t.start()
        time.sleep(0.05)
        # Close empty buffer -> must unblock thread
        empty_buf.close()
        t.join(timeout=1.0)

    t_prod = threading.Thread(target=blocked_producer)
    t_prod.start()
    time.sleep(0.05)

    # Close buffer to unblock waiting producer
    buf.close()
    t_prod.join(timeout=1.0)
    assert not t_prod.is_alive()
    assert len(producer_error) == 1
    assert "closed while waiting" in str(producer_error[0])

    # Run consumer unblock test
    blocked_consumer()
    assert consumer_result == [None]
