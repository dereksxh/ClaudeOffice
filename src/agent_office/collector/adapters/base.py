from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from agent_office.models import ControlCommand, EventRecord


@dataclass(frozen=True)
class AdapterCommandResult:
    applied: bool
    summary: str


class RuntimeAdapter(Protocol):
    machine_id: str

    def snapshot_events(self, now: datetime) -> list[EventRecord]:
        ...

    def apply_command(self, command: ControlCommand) -> AdapterCommandResult:
        ...
