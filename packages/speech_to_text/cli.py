"""
CLI Demo for Speech-to-Text & Segment Accumulator
Owner: Pavanchand R M (feature/speech-to-text - Team Lead)

Run this tool to see live simulated streaming transcription,
confidence scoring, and segment accumulation in your terminal.
"""
import time
import sys
from packages.speech_to_text.fake_transcriber import FakeTranscriberService
from packages.speech_to_text.accumulator import SegmentAccumulator


def run_demo():
    print("=" * 65)
    print("      AI Voice Co-Pilot - Speech-to-Text & Accumulator Demo     ")
    print("=" * 65)

    transcriber = FakeTranscriberService()
    session_id = f"demo-sess-{int(time.time())}"
    accumulator = SegmentAccumulator(session_id=session_id)

    print(f"\n[Session Initialized]: {session_id}")
    print(f"[Accumulator State]:   {accumulator.state.value}\n")

    # Demonstrate streaming chunks for Phrase 0
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
        time.sleep(0.15)  # simulate real-time speech delay

    print(f"\n[Buffered Segments]: {accumulator.count}")
    print(f"[Accumulator State]: {accumulator.state.value}")

    print("\n--- 2. Finalizing Spoken Utterance ---")
    utterance = accumulator.finalize_utterance()

    print(f"  [Utterance ID]: {utterance.id}")
    print(f"  [Full Text]:    \"{utterance.full_text}\"")
    print(f"  [Duration]:     {utterance.duration:.2f} seconds")
    print(f"  [Segments]:     {len(utterance.segments)}")
    print(f"  [Is Complete]:  {utterance.is_complete}")

    print(f"\n[Buffer Cleaned / Memory Released]: Current Segments = {accumulator.count}")
    print(f"[Accumulator Reset State]:          {accumulator.state.value}")

    print("\n--- 3. Single-shot Transcription Test ---")
    single_res = transcriber.transcribe(b"\x00" * 3200, phrase_index=1)
    print(f"  -> Transcribed: \"{single_res[0].text}\"")
    print(f"  -> Confidence:  {single_res[0].confidence:.2f}")

    print("\n" + "=" * 65)
    print("           Demo Completed Successfully (All Systems Green)      ")
    print("=" * 65)


if __name__ == "__main__":
    run_demo()
