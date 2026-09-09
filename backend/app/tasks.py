"""Background task queue abstraction. In-process for prototype; replace with Celery/RQ later."""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any


class TaskQueue(ABC):
    @abstractmethod
    async def enqueue(self, name: str, payload: dict[str, Any] | None = None) -> str: ...


class InProcessTaskQueue(TaskQueue):
    """Fire-and-forget asyncio tasks. Not durable across process restarts."""

    def __init__(self):
        self._handlers: dict[str, Callable[[dict[str, Any]], Awaitable[None]]] = {}
        self._jobs = 0

    def register(self, name: str, handler: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        self._handlers[name] = handler

    async def enqueue(self, name: str, payload: dict[str, Any] | None = None) -> str:
        handler = self._handlers.get(name)
        if handler is None:
            raise KeyError(f"Unknown background task: {name}")
        self._jobs += 1
        job_id = f"{name}-{self._jobs}"
        asyncio.create_task(handler(payload or {}), name=job_id)
        return job_id


task_queue = InProcessTaskQueue()
