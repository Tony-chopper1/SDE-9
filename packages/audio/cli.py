import time
from packages.audio.mock_mic import MockMicrophoneSource
from packages.audio.vad import SimpleVADDetector


def run_cli_demo(iterations: int = 10):
    print("=== SDK-9 Audio Pipeline & VAD CLI Demo ===")
    mic = MockMicrophoneSource()
    vad = SimpleVADDetector(energy_threshold=500.0)

    mic.start_streaming()
    print("Generating simulated audio stream (16kHz 16-bit Mono)...")

    for i in range(iterations):
        # Alternate between silence and speech
        is_speech = i % 2 == 1
        frame = mic.generate_synthetic_frame(is_speech=is_speech)
        vad_result = vad.evaluate_frame(frame)

        print(
            f"Frame #{frame.frame_index:02d} | "
            f"Bytes: {len(frame.data)} | "
            f"VAD State: {vad_result.state.value:<12} | "
            f"Energy: {vad_result.energy_level:8.2f} | "
            f"Speech Flag: {frame.is_speech}"
        )
        time.sleep(0.05)

    mic.stop_streaming()
    print("=== Audio Stream Finished Successfully ===")


if __name__ == "__main__":
    run_cli_demo()
