from __future__ import annotations

import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

from agent_office.collector.adapters.base import AdapterCommandResult
from agent_office.collector.adapters.files import append_command_outbox
from agent_office.models import Capability, EventRecord, EventType, RuntimeType
from agent_office.models import ControlCommand


def map_hermes_snapshot(machine_id: str, snapshot: dict[str, Any], timestamp: datetime) -> EventRecord:
    session_id = str(snapshot.get("session_id") or "hermes")
    capabilities = [Capability.REQUEST_REPORT.value, Capability.CONTINUE.value]
    if snapshot.get("can_accept_prompt"):
        capabilities.append(Capability.APPEND_PROMPT.value)

    raw = f"{machine_id}:{session_id}:{snapshot.get('status')}:{snapshot.get('summary')}"
    event_id = "hermes-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    return EventRecord(
        event_id=event_id,
        machine_id=machine_id,
        runtime_type=RuntimeType.HERMES,
        session_id=session_id,
        agent_id="main",
        event_type=EventType.SESSION_UPDATED,
        timestamp=timestamp,
        payload={
            "project_name": snapshot.get("project_name"),
            "status": snapshot.get("status", "working"),
            "progress_summary": snapshot.get("summary"),
            "capabilities": capabilities,
        },
        source_ref="hermes:snapshot",
    )


class HermesSnapshotFileAdapter:
    runtime_type = RuntimeType.HERMES

    def __init__(
        self,
        machine_id: str,
        snapshot_path: str | Path,
        command_outbox_path: str | Path | None = None,
    ) -> None:
        self.machine_id = machine_id
        self.snapshot_path = Path(snapshot_path)
        self.command_outbox_path = Path(command_outbox_path) if command_outbox_path else None

    def snapshot_events(self, now: datetime) -> list[EventRecord]:
        if not self.snapshot_path.exists():
            return []
        value = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
        if isinstance(value, list):
            snapshots = value
        elif isinstance(value, dict) and isinstance(value.get("sessions"), list):
            snapshots = value["sessions"]
        else:
            snapshots = [value]

        return [
            map_hermes_snapshot(self.machine_id, snapshot, now)
            for snapshot in snapshots
            if isinstance(snapshot, dict)
        ]

    def apply_command(self, command: ControlCommand) -> AdapterCommandResult:
        if command.target_machine_id != self.machine_id:
            return AdapterCommandResult(False, "command targets a different machine")
        if self.command_outbox_path is None:
            return AdapterCommandResult(False, "hermes command outbox is not configured")
        append_command_outbox(self.command_outbox_path, self.runtime_type, command)
        return AdapterCommandResult(True, f"{command.action.value} written to Hermes command outbox")
