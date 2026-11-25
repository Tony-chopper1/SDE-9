"""
OCR and Vision Adapter Interface and Mock Implementation.

Provides an abstract interface for multimodal vision/OCR processing and a
deterministic mock implementation that extracts code snippets and UI regions
from synthetic screen frames without external API dependencies.
"""
from __future__ import annotations

import abc
import time
from typing import Any, Dict, List, Optional

from packages.context_reasoning.exceptions import VisionProcessingError
from packages.context_reasoning.models import ScreenContext, VisionRegion, VisionResult


class BaseVisionAdapter(abc.ABC):
    """Abstract interface defining vision and OCR capabilities across screen frames."""

    @abc.abstractmethod
    def process_frame(self, frame: ScreenContext) -> VisionResult:
        """
        Analyze a screen frame and return extracted text and detected UI regions.

        Args:
            frame: ScreenContext instance containing image metadata or synthetic bytes.

        Returns:
            Structured VisionResult.
        """
        pass

    @abc.abstractmethod
    def extract_text(self, frame: ScreenContext) -> str:
        """
        Extract textual or code content from a screen frame.

        Args:
            frame: ScreenContext instance.

        Returns:
            Extracted text string.
        """
        pass

    @abc.abstractmethod
    def detect_regions(self, frame: ScreenContext) -> List[VisionRegion]:
        """
        Segment visual bounding box regions across the screen frame.

        Args:
            frame: ScreenContext instance.

        Returns:
            List of detected VisionRegion instances.
        """
        pass


class MockVisionAdapter(BaseVisionAdapter):
    """
    Deterministic simulated OCR and Vision processor for SDK-9.

    Features:
    - Zero external network or proprietary OCR dependencies.
    - Deterministic text extraction from synthetic frames and active window metadata.
    - Standard UI bounding box segmentation (editor, terminal, title bar).
    - Configurable simulated latency and failure injection for stress testing.
    """

    def __init__(
        self,
        default_confidence: float = 0.96,
        simulated_latency_ms: float = 15.0,
        fail_mode: bool = False,
    ) -> None:
        """
        Initialize the mock vision adapter.

        Args:
            default_confidence: Baseline confidence score (0.0 to 1.0).
            simulated_latency_ms: Artificial latency to record in metrics.
            fail_mode: If True, simulates hardware/driver failure by raising VisionProcessingError.
        """
        self.default_confidence: float = default_confidence
        self.simulated_latency_ms: float = max(0.0, simulated_latency_ms)
        self.fail_mode: bool = fail_mode

    def process_frame(self, frame: ScreenContext) -> VisionResult:
        """Process frame and return consolidated VisionResult along with observations."""
        if self.fail_mode:
            raise VisionProcessingError(f"Simulated vision hardware failure on frame '{frame.frame_id}'.")

        start = time.perf_counter()
        regions = self.detect_regions(frame)
        text = self.extract_text(frame)
        elapsed_ms = (time.perf_counter() - start) * 1000.0 + self.simulated_latency_ms

        # Build observations from regions
        observations = []
        for region in regions:
            obs = Observation(
                timestamp=time.time(),
                source=SourceReference(source_id=frame.frame_id, source_type="screen", title=region.label, is_trusted=False),
                content=region.text_content or "",
                metadata={"region_id": region.region_id, "label": region.label},
            )
            observations.append(obs)

        # Attach observations to the VisionResult via metadata (optional) or return separately.
        # Here we embed them in metadata for downstream processing.
        return VisionResult(
            frame_id=frame.frame_id or "unknown-frame",
            extracted_text=text,
            regions=regions,
            confidence=self.default_confidence,
            processing_time_ms=round(elapsed_ms, 2),
            metadata={
                "is_synthetic": frame.is_synthetic,
                "resolution": f"{frame.width}x{frame.height}",
                "engine": "SDK9_MockOCR_v2",
                "observations": observations,
            },
        )

    def extract_text(self, frame: ScreenContext) -> str:
        """Extract code or textual elements visible in the synthetic frame."""
        if self.fail_mode:
            raise VisionProcessingError("OCR pipeline failure during text extraction.")

        if frame.visible_text:
            return frame.visible_text

        if frame.active_window and frame.active_window.visible_snippet:
            return frame.active_window.visible_snippet

        # Synthetic fallback text
        return (
            "// Synthetic OCR Frame\n"
            "function processAudioStream(pcmData) {\n"
            "    console.log('SDK-9 Voice Co-Pilot active');\n"
            "}"
        )

    def detect_regions(self, frame: ScreenContext) -> List[VisionRegion]:
        """Detect standard IDE/OS visual regions across frame dimensions."""
        if self.fail_mode:
            raise VisionProcessingError("Region detection failed in mock vision adapter.")

        w = frame.width
        h = frame.height

        regions: List[VisionRegion] = [
            VisionRegion(
                label="title_bar",
                x=0,
                y=0,
                width=w,
                height=min(40, int(h * 0.05)),
                confidence=0.99,
                text_content=frame.active_window.window_title if frame.active_window else "IDE Window",
            ),
            VisionRegion(
                label="code_editor",
                x=0,
                y=min(40, int(h * 0.05)),
                width=int(w * 0.70),
                height=int(h * 0.70),
                confidence=self.default_confidence,
                text_content=self.extract_text(frame),
            ),
            VisionRegion(
                label="terminal_console",
                x=0,
                y=int(h * 0.75),
                width=w,
                height=int(h * 0.25),
                confidence=0.94,
                text_content="[SDK-9 Gateway] Server listening on port 8000. All tests passed.",
            ),
        ]
        return regions
