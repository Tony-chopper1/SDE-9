"""
Unit tests for deterministic MockMicrophoneSource and AudioSource.
Located in packages/audio/tests/ per SDK-9 testing strategy.

Verifies:
- Lifecycle (open, read, close, is_active, start_streaming, stop_streaming)
- Context manager protocol
- Deterministic frame generation and byte reproducibility
- Monotonically increasing sequence_number and frame_index
- Consistently advancing audio-relative timestamp_ms
- Support for 20ms (640 bytes) and 30ms (960 bytes) frames
- Explicit end-of-stream behavior (returns None, never empty frame)
- Backward-compatible alias MockMicSource and packages.audio.source re-exports
"""
import pytest

from packages.audio.exceptions import AudioSourceError
from packages.audio.models import AudioConfig
from packages.audio.mock_mic import AudioSource, MockMicSource, MockMicrophoneSource
import packages.audio.source as source_module


def test_mock_mic_lifecycle_and_eos():
    """Verify open, close, active state transitions, and explicit EOF (None)."""
    mic = MockMicrophoneSource(max_frames=2)
    assert not mic.is_active
    assert not mic.is_streaming

    # Reading while closed raises AudioSourceError
    with pytest.raises(AudioSourceError):
        mic.read_frame()

    mic.open()
    assert mic.is_active
    assert mic.is_streaming

    # Read frame 0
    f0 = mic.read_frame()
    assert f0 is not None
    assert f0.sequence_number == 0
    assert f0.frame_index == 0
    assert f0.timestamp_ms == 0.0

    # Read frame 1
    f1 = mic.read_frame()
    assert f1 is not None
    assert f1.sequence_number == 1
    assert f1.frame_index == 1
    assert f1.timestamp_ms == 30.0  # default 30ms

    # Read past max_frames: must return None (explicit EOF, never empty frame)
    eof = mic.read_frame()
    assert eof is None
    assert not mic.is_active

    mic.close()
    assert not mic.is_active
    assert not mic.is_streaming


def test_mock_mic_team_streaming_interface():
    """Verify team methods start_streaming(), stop_streaming(), generate_synthetic_frame()."""
    mic = MockMicrophoneSource()
    assert not mic.is_streaming

    mic.start_streaming()
    assert mic.is_streaming
    assert mic.is_active

    # Speech frame
    speech_frame = mic.generate_synthetic_frame(is_speech=True)
    assert speech_frame.is_speech is True
    assert len(speech_frame.data) == 960
    assert speech_frame.calculate_rms() > 5000.0

    # Silent frame
    silent_frame = mic.generate_synthetic_frame(is_speech=False)
    assert silent_frame.is_speech is False
    assert len(silent_frame.data) == 960
    assert silent_frame.calculate_rms() == 0.0

    mic.stop_streaming()
    assert not mic.is_streaming
    assert not mic.is_active


def test_mock_mic_20ms_and_30ms_frame_sizes():
    """Verify mock mic correctly produces both 20ms (640B) and 30ms (960B) frames at 16kHz mono."""
    # 1. 20ms frames (640 bytes) - provisional STT contract
    cfg20 = AudioConfig(sample_rate=16000, channels=1, format="s16le", frame_duration_ms=20)
    with MockMicrophoneSource(config=cfg20, max_frames=3) as mic20:
        frames20 = list(mic20.stream())
        assert len(frames20) == 3
        for i, frame in enumerate(frames20):
            assert frame.sequence_number == i
            assert frame.frame_index == i
            assert frame.timestamp_ms == float(i * 20)
            assert len(frame.data) == 640
            assert len(frame.audio_data) == 640
            assert frame.frame_duration_ms == 20

    # 2. 30ms frames (960 bytes) - team default
    cfg30 = AudioConfig(sample_rate=16000, channels=1, format="s16le", frame_duration_ms=30)
    with MockMicrophoneSource(config=cfg30, max_frames=3) as mic30:
        frames30 = list(mic30.stream())
        assert len(frames30) == 3
        for i, frame in enumerate(frames30):
            assert frame.sequence_number == i
            assert frame.frame_index == i
            assert frame.timestamp_ms == float(i * 30)
            assert len(frame.data) == 960
            assert len(frame.audio_data) == 960
            assert frame.frame_duration_ms == 30


def test_mock_mic_determinism():
    """Verify that identical configurations and patterns produce identical audio bytes and metadata."""
    config = AudioConfig(sample_rate=16000, frame_duration_ms=20)

    mic1 = MockMicrophoneSource(config=config, pattern="speech", max_frames=10, seed=42)
    mic2 = MockMicrophoneSource(config=config, pattern="speech", max_frames=10, seed=42)

    with mic1, mic2:
        frames1 = list(mic1.stream())
        frames2 = list(mic2.stream())

    assert len(frames1) == 10
    assert len(frames2) == 10

    for f1, f2 in zip(frames1, frames2):
        assert f1.model_dump() == f2.model_dump()
        assert f1.frame_id == f2.frame_id
        assert f1.timestamp == f2.timestamp
        assert f1.timestamp_utc == f2.timestamp_utc
        assert f1.sequence_number == f2.sequence_number
        assert f1.timestamp_ms == f2.timestamp_ms
        assert f1.data == f2.data
        assert f1.calculate_rms() == f2.calculate_rms()


def test_mock_mic_strict_two_runs_identical_outputs():
    """CEO Requirement 3: Automated test proving two runs with identical inputs produce identical outputs."""
    # First run
    mic_run_1 = MockMicrophoneSource(
        pattern="alternating",
        max_frames=8,
        seed=12345,
        start_timestamp=1793491200.0,
    )
    with mic_run_1:
        frames_run_1 = [frame.model_dump() for frame in mic_run_1.stream()]

    # Second run with identical configuration and seed
    mic_run_2 = MockMicrophoneSource(
        pattern="alternating",
        max_frames=8,
        seed=12345,
        start_timestamp=1793491200.0,
    )
    with mic_run_2:
        frames_run_2 = [frame.model_dump() for frame in mic_run_2.stream()]

    assert len(frames_run_1) == 8
    assert len(frames_run_2) == 8
    # Exact full serialized equality across all 8 frames (IDs, timestamps, metadata, and PCM data)
    assert frames_run_1 == frames_run_2
    for f1, f2 in zip(frames_run_1, frames_run_2):
        assert f1["frame_id"] == f2["frame_id"]
        assert f1["timestamp"] == f2["timestamp"]
        assert f1["timestamp_utc"] == f2["timestamp_utc"]
        assert f1["sequence_number"] == f2["sequence_number"]
        assert f1["data"] == f2["data"]

    # Verify seed variation produces distinct frame IDs while preserving deterministic PCM and timestamps
    mic_run_3 = MockMicrophoneSource(
        pattern="alternating",
        max_frames=8,
        seed=99999,
        start_timestamp=1793491200.0,
    )
    with mic_run_3:
        frames_run_3 = [frame.model_dump() for frame in mic_run_3.stream()]
    assert frames_run_3[0]["frame_id"] != frames_run_1[0]["frame_id"]
    assert frames_run_3[0]["timestamp"] == frames_run_1[0]["timestamp"]
    # PCM waveform is synthesized mathematically and remains deterministic
    assert frames_run_3[0]["data"] == frames_run_1[0]["data"]


def test_mock_mic_patterns():
    """Verify speech, silence, alternating, and custom pattern behaviors."""
    config = AudioConfig(sample_rate=16000, frame_duration_ms=20)

    # 1. Pure silence pattern
    with MockMicrophoneSource(config=config, pattern="silence", max_frames=5) as mic:
        for frame in mic.stream():
            assert frame.is_speech is False
            assert frame.calculate_rms() == 0.0
            assert frame.calculate_dbfs() == -100.0

    # 2. Pure speech pattern
    with MockMicrophoneSource(config=config, pattern="speech", max_frames=5) as mic:
        for frame in mic.stream():
            assert frame.is_speech is True
            assert frame.calculate_rms() > 5000.0
            assert frame.calculate_dbfs() > -30.0

    # 3. Alternating pattern (600ms speech / 600ms silence cycles)
    # 20ms frames -> 30 frames speech (0-600ms), 30 frames silence (600-1200ms)
    with MockMicrophoneSource(config=config, pattern="alternating", max_frames=40) as mic:
        frames = list(mic.stream())
        assert len(frames) == 40
        assert frames[0].is_speech is True
        assert frames[29].is_speech is True
        assert frames[30].is_speech is False
        assert frames[39].is_speech is False

    # 4. Custom pattern: 40ms silence then 40ms speech
    custom = [("silence", 40), ("speech", 40)]
    with MockMicrophoneSource(config=config, pattern="custom", custom_timeline=custom, max_frames=4) as mic:
        frames = list(mic.stream())
        assert len(frames) == 4
        # Frames 0 and 1 (0-40ms): silence
        assert frames[0].is_speech is False
        assert frames[0].calculate_rms() == 0.0
        assert frames[1].is_speech is False
        assert frames[1].calculate_rms() == 0.0
        # Frames 2 and 3 (40-80ms): speech
        assert frames[2].is_speech is True
        assert frames[2].calculate_rms() > 5000.0
        assert frames[3].is_speech is True
        assert frames[3].calculate_rms() > 5000.0


def test_mock_mic_duration_seconds():
    """Verify duration_seconds calculates exact max_frames."""
    config = AudioConfig(sample_rate=16000, frame_duration_ms=20)
    # 0.1s / 20ms = 5 frames
    mic = MockMicrophoneSource(config=config, duration_seconds=0.1)
    assert mic.max_frames == 5
    with mic:
        frames = list(mic.stream())
    assert len(frames) == 5


def test_mock_mic_unknown_pattern_error():
    """Verify error on unknown pattern specification."""
    with pytest.raises(AudioSourceError) as exc:
        MockMicrophoneSource(pattern="non_existent_pattern")
    assert "Unknown mock mic pattern" in str(exc.value)
    assert exc.value.code == "AUDIO_SOURCE_ERROR"


def test_source_reexports_and_alias():
    """Verify MockMicSource alias and packages.audio.source re-exports."""
    assert MockMicSource is MockMicrophoneSource
    assert source_module.AudioSource is AudioSource
    assert source_module.MockMicrophoneSource is MockMicrophoneSource
    assert source_module.MockMicSource is MockMicrophoneSource
