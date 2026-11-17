"""
SDK-9 AI Voice Co-Pilot - Speech-to-Text & Segment Accumulator CLI Demo

Interactive tool demonstrating real-time simulated streaming transcription,
dynamic confidence scoring, out-of-order chunk resolution, audio preprocessing
(resampling & normalization), duplicate suppression, and full pipeline orchestration.
"""

from __future__ import annotations

import struct
import sys
import time

from packages.speech_to_text.accumulator import SegmentAccumulator
from packages.speech_to_text.fake_transcriber import FakeTranscriberService
from packages.speech_to_text.models import TranscriptSegment
from packages.speech_to_text.orchestrator import SpeechToTextOrchestrator
from packages.speech_to_text.preprocessor import AudioPreprocessor
from packages.speech_to_text.reconciler import TranscriptReconciler


def run_demo() -> None:
    print("=" * 70)
    print("      AI Voice Co-Pilot - Speech-to-Text & Accumulator Demo (Week 2)      ")
    print("=" * 70)

    transcriber = FakeTranscriberService()
    session_id = f"demo-sess-{int(time.time())}"
    accumulator = SegmentAccumulator(session_id=session_id)

    print(f"\n[Session Initialized]: {session_id}")
    print(f"[Accumulator State]:   {accumulator.state.value}\n")

    # 1. Streaming word-by-word transcription
    print("--- 1. Simulating Word-by-Word Streaming Audio Input ---")
    chunks = transcriber.simulate_streaming_chunks(phrase_index=0)

    for chunk in chunks:
        status_label = "FINAL" if chunk.is_final else "INTERIM"
        print(
            f"  -> Received [{status_label:<7}] | "
            f"Confidence: {chunk.confidence:.2f} | "
            f"Time: [{chunk.start_time:.1f}s - {chunk.end_time:.1f}s] | "
            f'"{chunk.text}"'
        )
        accumulator.add_segment(chunk)
        time.sleep(0.05)

    print(f"\n[Buffered Segments]: {accumulator.count}")
    print(f"[Accumulator State]: {accumulator.state.value}")

    print("\n--- 2. Finalizing Spoken Utterance ---")
    utterance = accumulator.finalize_utterance()
    print(f"  [Utterance ID]: {utterance.id}")
    print(f'  [Full Text]:    "{utterance.full_text}"')
    print(f"  [Duration]:     {utterance.duration:.2f} seconds")
    print(f"  [Segments]:     {len(utterance.segments)}")
    print(f"  [Is Complete]:  {utterance.is_complete}")

    # 3. Audio Preprocessing & Resampling Demo
    print("\n--- 3. Audio Preprocessing & Resampling (48 kHz -> 16 kHz) ---")
    preproc = AudioPreprocessor()
    synthetic_48k = struct.pack("<1200h", *([800] * 1200))  # 25ms of 48kHz audio
    resampled = preproc.process(synthetic_48k, source_sample_rate=48000, channels=1)
    print(f"  -> Input:  {len(synthetic_48k)} bytes @ 48,000 Hz")
    print(f"  -> Output: {len(resampled)} bytes @ 16,000 Hz (mono s16le, normalized)")
    print(f"  -> Energy: {preproc.calculate_rms_db(resampled):.2f} dBFS")

    # 4. Transcript Reconciler Demo
    print("\n--- 4. Monotonic Ordering & Duplicate Suppression ---")
    reconciler = TranscriptReconciler(session_id="reconciler-demo")
    seg2 = TranscriptSegment(id="s2", text="world", start_time=1.0, end_time=1.5, is_final=True)
    seg1 = TranscriptSegment(id="s1", text="Hello", start_time=0.0, end_time=0.9, is_final=True)
    reconciler.process_segment(seg2)
    reconciler.process_segment(seg1)
    reconciler.process_segment(seg1)  # Duplicate!
    print(f"  -> Finalized Text:  \"{reconciler.get_finalized_text()}\"")
    print(f"  -> Duplicates Dropped: {reconciler.duplicate_count}")

    # 5. Full Orchestrator Pipeline Demo
    print("\n--- 5. End-to-End Orchestrator Pipeline Demo ---")
    orchestrator = SpeechToTextOrchestrator(session_id="e2e-demo")
    orchestrator.start()
    test_frame = b"\x08\x00" * 480  # 960 bytes (30ms at 16kHz)
    for _ in range(4):
        orchestrator.push_audio(test_frame, sample_rate=16000)

    final_utt = orchestrator.stop()
    print(f"  -> Frames Ingested:    {orchestrator.total_frames_processed}")
    print(f"  -> Bytes Ingested:     {orchestrator.total_audio_bytes_ingested} bytes")
    print(f"  -> Synthesized Result: \"{final_utt.full_text}\"")
    print(f"  -> Orchestrator State: {orchestrator.state}")

    print("\n" + "=" * 70)
    print("           Demo Completed Successfully (All Systems Green)      ")
    print("=" * 70)


if __name__ == "__main__":
    run_demo()
