
import asyncio
from uuid import UUID

from backend.schemas.events import EventCreate, EventRecord


class EventService:
    def __init__(self):
        self.events: dict[UUID, list[EventRecord]] = {}
        self.subscribers: dict[UUID, set[asyncio.Queue]] = {}
        self.lock = asyncio.Lock()

    async def publish_event(
        self,
        session_id: UUID,
        data: EventCreate,
    ) -> EventRecord:
        event = EventRecord(
            session_id=session_id,
            event_type=data.event_type,
            schema_version=data.schema_version,
            producer=data.producer,
            payload=data.payload,
        )

        async with self.lock:
            self.events.setdefault(session_id, []).append(event)

            for queue in self.subscribers.get(session_id, set()):
                queue.put_nowait(event)

        return event

    async def stream_events(
        self,
        session_id: UUID,
        after_event_id: UUID | None = None,
    ):
        queue = asyncio.Queue()

        async with self.lock:
            history = list(self.events.get(session_id, []))

            if after_event_id is not None:
                cursor_index = next(
                    (
                        index
                        for index, event in enumerate(history)
                        if event.event_id == after_event_id
                    ),
                    None,
                )

                if cursor_index is None:
                    raise ValueError("Event replay cursor not found")

                history = history[cursor_index + 1:]

            # Register while holding the same lock used by publishers.
            # This prevents events being lost between replay and live streaming.
            self.subscribers.setdefault(session_id, set()).add(queue)

        try:
            for event in history:
                yield event

            while True:
                event = await queue.get()
                yield event

        finally:
            async with self.lock:
                subscribers = self.subscribers.get(session_id, set())
                subscribers.discard(queue)

                if not subscribers:
                    self.subscribers.pop(session_id, None)

    def get_events(self, session_id: UUID):
        return list(self.events.get(session_id, []))


event_service = EventService()
