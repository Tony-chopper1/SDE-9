"""
Parity and consistency tests between Python models and TypeScript definitions.
Located in packages/audio/tests/ per SDK-9 testing strategy.

Verifies:
- Python Pydantic models (models.py) and TypeScript interfaces (types.ts) have matching fields
- Enum values parity (VADState)
- Execution of TypeScript runtime validation test (test_types.ts) via Node 24
"""
import os
import re
import shutil
import subprocess
from pathlib import Path
import pytest

from packages.audio.models import (
    AudioConfig,
    AudioFrame,
    EventEnvelope,
    VADEvent,
    VADResult,
    VADState,
)


def _load_ts_content() -> str:
    types_path = Path(__file__).resolve().parent.parent / "types.ts"
    assert types_path.exists(), f"TypeScript definitions file not found at {types_path}"
    return types_path.read_text(encoding="utf-8")


def test_vad_state_enum_parity():
    """Verify TypeScript VADState const object matches Python VADState enum values."""
    ts_content = _load_ts_content()
    for state in VADState:
        pattern = rf"{state.name}\s*:\s*['\"]{state.value}['\"]"
        assert re.search(pattern, ts_content), f"VADState.{state.name} missing or mismatched in types.ts"


def test_audio_config_field_parity():
    """Verify AudioConfig fields in Python match TypeScript interface."""
    ts_content = _load_ts_content()
    py_fields = set(AudioConfig.model_fields.keys())
    assert py_fields == {"sample_rate", "bit_depth", "channels", "format", "frame_duration_ms"}
    for f in py_fields:
        assert re.search(rf"\b{f}\s*:\s*number|\b{f}\s*:\s*string", ts_content), (
            f"AudioConfig field '{f}' missing from TypeScript definition"
        )


def test_audio_frame_field_parity():
    """Verify AudioFrame fields in Python match TypeScript interface."""
    ts_content = _load_ts_content()
    py_fields = set(AudioFrame.model_fields.keys())
    expected_fields = {
        "data",
        "timestamp",
        "sample_rate",
        "frame_index",
        "is_speech",
        "audio_data",
        "channels",
        "format",
        "frame_duration_ms",
        "sequence_number",
        "timestamp_ms",
        "frame_id",
        "timestamp_utc",
    }
    assert py_fields == expected_fields
    for f in py_fields:
        assert re.search(rf"\b{f}\??\s*:", ts_content), (
            f"AudioFrame field '{f}' missing from TypeScript definition"
        )


def test_vad_result_field_parity():
    """Verify VADResult fields in Python match TypeScript interface."""
    ts_content = _load_ts_content()
    py_fields = set(VADResult.model_fields.keys())
    assert py_fields == {"is_speech", "confidence", "energy_db", "metadata"}
    for f in py_fields:
        assert re.search(rf"\b{f}\??\s*:", ts_content), (
            f"VADResult field '{f}' missing from TypeScript definition"
        )


def test_vad_event_field_parity():
    """Verify internal VADEvent fields in Python match TypeScript interface."""
    ts_content = _load_ts_content()
    py_fields = set(VADEvent.model_fields.keys())
    assert py_fields == {"state", "timestamp", "energy_level", "confidence", "frame_index", "timestamp_ms"}
    for f in py_fields:
        assert re.search(rf"\b{f}\??\s*:", ts_content), (
            f"VADEvent field '{f}' missing from TypeScript definition"
        )


def test_event_envelope_field_parity():
    """Verify shared EventEnvelope fields in Python match TypeScript interface."""
    ts_content = _load_ts_content()
    py_fields = set(EventEnvelope.model_fields.keys())
    assert py_fields == {
        "event_id",
        "event_type",
        "schema_version",
        "session_id",
        "correlation_id",
        "timestamp",
        "producer",
        "payload",
    }
    for f in py_fields:
        assert re.search(rf"\b{f}\s*:", ts_content), (
            f"EventEnvelope field '{f}' missing from TypeScript definition"
        )


def test_node_runs_typescript_validation():
    """Verify Node 24 native type stripping executes test_types.ts without error."""
    # Locate node binary
    node_bin = shutil.which("node")
    if not node_bin:
        winget_node = Path(
            r"C:\Users\SATWIK\AppData\Local\Microsoft\WinGet\Packages\OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe\node-v24.19.0-win-x64\node.exe"
        )
        if winget_node.exists():
            node_bin = str(winget_node)

    if not node_bin:
        pytest.skip("Node.js binary not available in this environment")

    test_script = Path(__file__).resolve().parent / "test_types.ts"
    assert test_script.exists()

    result = subprocess.run(
        [node_bin, "--experimental-strip-types", str(test_script)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, f"Node test_types.ts failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    assert "All TypeScript type tests passed successfully" in result.stdout
