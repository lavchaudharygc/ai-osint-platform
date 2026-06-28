"""Lightweight in-process event bus for investigation status updates."""

from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

EventHandler = Callable[[dict[str, Any]], Awaitable[None]]


class EventBus:
    """Async publish/subscribe helper used before introducing a broker."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        self._subscribers[event_name].append(handler)

    async def publish(self, event_name: str, payload: dict[str, Any]) -> None:
        for handler in self._subscribers[event_name]:
            await handler(payload)


event_bus = EventBus()
