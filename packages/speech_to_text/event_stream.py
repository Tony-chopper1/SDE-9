"""
Event Stream Integration for Speech-to-Text Module.
Connects STT transcript events to backend EventService streams (SSE)
and provides audio event consumption utilities.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID

from packages.speech_to_text.models import TranscriptEvent


class TranscriptEventBridge:
    """
    Bridges Speech-to-Text transcript events into the Backend Event Stream.
    Allows end-to-end event propagation into SSE / EventService without modifying backend code.
    """

    def __init__(
        self,
        event_service: Optional[Any] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        on_event_published: Optional[Callable[[TranscriptEvent, Any], None]] = None,
    ) -> None:
        self.event_service = event_service
        self.loop = loop
        self.on_event_published = on_event_published
        self.published_events: List[TranscriptEvent] = []

    def on_transcript_event(self, event: TranscriptEvent) -> None:
        """Synchronous event callback suitable for SpeechToTextOrchestrator.on_event."""
        self.published_events.append(event)

        if self.event_service is not None:
            self._dispatch_to_event_service(event)

        if self.on_event_published:
            try:
                self.on_event_published(event, self.event_service)
            except Exception:
                pass

    def _dispatch_to_event_service(self, event: TranscriptEvent) -> None:
        """Dispatch event into backend event service safely across sync/async boundaries."""
        try:
            # Parse session ID to UUID if needed by backend
            try:
                session_uuid = UUID(str(event.session_id))
            except (ValueError, TypeError):
                session_uuid = event.session_id

            # Lazy import backend EventCreate if available
            try:
                from backend.schemas.events import EventCreate
                backend_payload = event.to_backend_payload()
                data = EventCreate(
                    event_type=backend_payload["event_type"],
                    schema_version=backend_payload["schema_version"],
                    producer=backend_payload["producer"],
                    payload=backend_payload["payload"],
                )
            except ImportError:
                data = event.to_backend_payload()

            publish_fn = getattr(self.event_service, "publish_event", None)
            if publish_fn is None:
                return

            if asyncio.iscoroutinefunction(publish_fn):
                loop = self.loop
                if loop is None:
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        loop = None

                if loop and loop.is_running():
                    try:
                        loop.create_task(publish_fn(session_uuid, data))
                    except RuntimeError:
                        asyncio.run_coroutine_threadsafe(
                            publish_fn(session_uuid, data),
                            loop,
                        )
                else:
                    asyncio.run(publish_fn(session_uuid, data))
            else:
                publish_fn(session_uuid, data)
        except Exception:
            # Safe boundary - never leak unhandled exceptions out of event callback
            pass

    async def async_publish_event(self, event: TranscriptEvent) -> Any:
        """Asynchronously publish a transcript event to the backend EventService."""
        self.published_events.append(event)
        if self.event_service is None:
            return None

        try:
            session_uuid = UUID(str(event.session_id))
        except (ValueError, TypeError):
            session_uuid = event.session_id

        try:
            from backend.schemas.events import EventCreate
            backend_payload = event.to_backend_payload()
            data = EventCreate(
                event_type=backend_payload["event_type"],
                schema_version=backend_payload["schema_version"],
                producer=backend_payload["producer"],
                payload=backend_payload["payload"],
            )
        except ImportError:
            data = event.to_backend_payload()

        publish_fn = getattr(self.event_service, "publish_event", None)
        if publish_fn is None:
            return None

        if asyncio.iscoroutinefunction(publish_fn):
            return await publish_fn(session_uuid, data)
        return publish_fn(session_uuid, data)
