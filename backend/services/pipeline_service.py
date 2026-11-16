
"""
SDK-9 Week 3 - Mock Pipeline Integration Service.

Connects Audio/VAD, Speech-to-Text, Context/Reasoning,
and Agentic Workflow using the existing package implementations.
"""

from uuid import UUID

from packages.audio import AudioConfig, AudioFrame, MockVAD
from packages.speech_to_text import FakeTranscriberService
from packages.context_reasoning import (
    ContextManager,
    MockReasoningService,
)
from packages.agentic_workflow import (
    AgentState,
    AgentStateMachine,
    PermissionScope,
    SafetyLevel,
    ToolRegistry,
    WorkflowStep,
)


class PipelineService:
    """Coordinates the SDK-9 mock processing pipeline."""

    def __init__(self):
        self.audio_config = AudioConfig()
        self.transcriber = FakeTranscriberService()
        self.reasoning_service = MockReasoningService()
        self.tool_registry = ToolRegistry(load_defaults=True)

    def process_audio(
        self,
        session_id: UUID,
        audio_data: bytes | None = None,
        correlation_id: str | None = None,
    ) -> dict:
        """Process audio through all available mock modules."""

        if audio_data is None:
            audio_data = b"\x01" * 6400

        if not audio_data:
            raise ValueError("Audio input cannot be empty")

        # 1. Audio and VAD
        frame_size = (
            self.audio_config.sample_rate
            * self.audio_config.channels
            * self.audio_config.bit_depth
            // 8
            * self.audio_config.frame_duration_ms
            // 1000
        )

        # AudioFrame requires exactly one frame of audio.
        frame_data = audio_data[:frame_size]

        if len(frame_data) < frame_size:
            frame_data += b"\x00" * (frame_size - len(frame_data))

        vad = MockVAD(scripted_decisions=[True])

        frame = AudioFrame(
            data=frame_data,
            sample_rate=self.audio_config.sample_rate,
            channels=self.audio_config.channels,
            frame_index=0,
            sequence_number=0,
            is_speech=True,
        )

        vad_result = vad.process_frame(frame)

        # 2. Speech-to-Text
        transcript_segments = []

        if vad_result.is_speech:
            transcript_segments = self.transcriber.transcribe(
                audio_data,
                phrase_index=0,
            )

        transcript = " ".join(
            segment.text for segment in transcript_segments
        ).strip()

        if not transcript:
            transcript = "No speech detected"

        # 3. Context and Reasoning
        context_manager = ContextManager(
            session_id=str(session_id)
        )

        context_manager.update_user_query(transcript)

        reasoning_result = self.reasoning_service.reason(
            context_manager.get_context()
        )

        # 4. Agentic Workflow policy evaluation
        workflow_result = {
            "status": "not_required",
            "tool_name": None,
            "permission_granted": False,
            "approval_required": False,
            "plan_created": False,
        }

        if (
            reasoning_result.requires_tool
            and reasoning_result.planned_tool_name
        ):
            tool_name = reasoning_result.planned_tool_name

            if self.tool_registry.is_registered(tool_name):
                spec = self.tool_registry.get_spec(tool_name)

                safety_level = getattr(
                    spec,
                    "safety_level",
                    SafetyLevel.A,
                )

                permission_granted = self.tool_registry.check_permission(
                    tool_name,
                    {PermissionScope.READ_ONLY},
                )

                workflow_result.update(
                    {
                        "status": "policy_evaluated",
                        "tool_name": tool_name,
                        "permission_granted": permission_granted,
                        "approval_required": safety_level
                        in {SafetyLevel.C, SafetyLevel.D},
                    }
                )

                if permission_granted:
                    agent = AgentStateMachine()

                    if agent.can_transition_to(AgentState.PLANNING):
                        agent.transition_to(AgentState.PLANNING)

                        step = WorkflowStep(
                            step_number=1,
                            description=(
                                f"Execute approved tool: {tool_name}"
                            ),
                            tool_name=tool_name,
                            parameters=(
                                reasoning_result.tool_parameters or {}
                            ),
                            safety_level=safety_level,
                        )

                        agent.build_plan(
                            session_id=str(session_id),
                            goal=transcript,
                            steps=[step],
                        )

                        workflow_result["plan_created"] = True
            else:
                workflow_result["status"] = "tool_not_registered"

        return {
            "session_id": str(session_id),
            "correlation_id": correlation_id,
            "mock_mode": True,
            "audio": {
                "received_bytes": len(audio_data),
                "frame_bytes": frame_size,
                "speech_detected": vad_result.is_speech,
                "vad_confidence": vad_result.confidence,
            },
            "transcription": {
                "text": transcript,
                "segments": [
                    segment.model_dump(mode="json")
                    for segment in transcript_segments
                ],
            },
            "reasoning": {
                "intent": reasoning_result.intent,
                "requires_tool": reasoning_result.requires_tool,
                "planned_tool_name": reasoning_result.planned_tool_name,
                "tool_parameters": reasoning_result.tool_parameters,
                "direct_response": reasoning_result.direct_response,
                "confidence": reasoning_result.confidence,
            },
            "workflow": workflow_result,
        }


pipeline_service = PipelineService()
