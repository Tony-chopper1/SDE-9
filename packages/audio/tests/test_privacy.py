"""
Privacy and Zero-Disk-Write verification tests for SDK-9 Audio & VAD module.
Owner: Satwik A (features/Satwik-week4) - Week 4 (Days 22-24)

Verifies:
1. Default mock microphone streaming does not invoke any disk write operations.
2. Full audio processing pipeline (VAD, Session Pipeline, Event Envelopes, STT Bridge)
   operates 100% in-memory with zero filesystem persistence.
3. AudioFrame and AudioChunk data models do not save to disk.
4. BoundedAudioBuffer drops frames strictly in-memory without spooling to disk.
"""
from __future__ import annotations

import builtins
from unittest.mock import patch
import pytest

from packages.audio.buffer import BackpressureStrategy, BoundedAudioBuffer
from packages.audio.events import AudioSessionPipeline
from packages.audio.mock_mic import MockMicrophoneSource
from packages.audio.models import AudioConfig, AudioFrame, AudioChunk
from packages.audio.stt_bridge import AudioSTTBridge
from packages.audio.vad import EnergyVAD


def test_mock_mic_streaming_zero_disk_writes():
    """Verify that MockMicrophoneSource streams 100+ frames without opening any file for writing."""
    config = AudioConfig(sample_rate=16000, frame_duration_ms=20)
    mic = MockMicrophoneSource(config=config, pattern="alternating", max_frames=100)

    write_calls = []
    original_open = builtins.open

    def monitored_open(*args, **kwargs):
        # Inspect mode parameter (2nd positional arg or keyword 'mode')
        mode = kwargs.get("mode", "")
        if not mode and len(args) > 1:
            mode = args[1]
        mode_str = str(mode)
        # Check if opened for writing or appending
        if any(flag in mode_str for flag in ("w", "a", "+", "x")):
            write_calls.append((args, kwargs))
        return original_open(*args, **kwargs)

    with patch("builtins.open", side_effect=monitored_open):
        frames = []
        with mic:
            for frame in mic.stream():
                frames.append(frame)

    assert len(frames) == 100
    assert len(write_calls) == 0, f"Unexpected disk write operations detected: {write_calls}"


def test_end_to_end_pipeline_and_stt_bridge_zero_disk_writes():
    """Verify that end-to-end pipeline through STT bridge never persists audio to disk."""
    config = AudioConfig(sample_rate=16000, frame_duration_ms=20)
    mic = MockMicrophoneSource(config=config, pattern="speech", max_frames=50)
    vad = EnergyVAD(threshold_db=-42.0)
    pipeline = AudioSessionPipeline(session_id="privacy-sess-001", vad=vad)
    bridge = AudioSTTBridge(session_id="privacy-sess-001")
    pipeline.dispatcher.subscribe(bridge.handle_event)

    write_calls = []
    original_open = builtins.open

    def monitored_open(*args, **kwargs):
        mode = kwargs.get("mode", "")
        if not mode and len(args) > 1:
            mode = args[1]
        mode_str = str(mode)
        if any(flag in mode_str for flag in ("w", "a", "+", "x")):
            write_calls.append((args, kwargs))
        return original_open(*args, **kwargs)

    with patch("builtins.open", side_effect=monitored_open):
        with mic:
            for frame in mic.stream():
                pipeline.process_frame(frame)
        pipeline.flush()

    assert bridge.telemetry["speech_chunks_forwarded"] > 0
    assert len(write_calls) == 0, f"Unexpected disk write operations in pipeline: {write_calls}"


def test_bounded_buffer_drop_zero_disk_writes():
    """Verify that BoundedAudioBuffer drops overflow frames in memory without spooling to disk."""
    config = AudioConfig(sample_rate=16000, frame_duration_ms=20)
    buffer = BoundedAudioBuffer(max_frames=5, strategy=BackpressureStrategy.DROP_OLDEST)

    write_calls = []
    original_open = builtins.open

    def monitored_open(*args, **kwargs):
        mode = kwargs.get("mode", "")
        if not mode and len(args) > 1:
            mode = args[1]
        mode_str = str(mode)
        if any(flag in mode_str for flag in ("w", "a", "+", "x")):
            write_calls.append((args, kwargs))
        return original_open(*args, **kwargs)

    with patch("builtins.open", side_effect=monitored_open):
        # Push 15 frames into 5-capacity buffer (10 dropped)
        for seq in range(15):
            data = b"\x00\x01" * 320
            f = AudioFrame(data=data, sequence_number=seq, frame_duration_ms=20)
            buffer.push(f)

    tele = buffer.get_telemetry()
    assert tele.frames_dropped == 10
    assert len(write_calls) == 0, f"Buffer drop operations triggered disk writes: {write_calls}"


def test_audio_models_in_memory_only():
    """Verify AudioFrame and AudioChunk serialize to in-memory dictionaries without disk paths."""
    pcm = b"\x10\x20" * 320
    frame = AudioFrame(data=pcm, sequence_number=1, frame_duration_ms=20)
    d = frame.to_dict(include_raw_bytes=True)

    assert "audio_data_base64" in d
    assert "file_path" not in d
    assert "disk_path" not in d

    chunk = AudioChunk(data=pcm, sequence_number=1, frame_duration_ms=20)
    cd = chunk.to_dict(include_raw_bytes=True)
    assert cd["frame_id"] == chunk.frame_id
    assert "audio_data_base64" in cd
    assert "file_path" not in cd
