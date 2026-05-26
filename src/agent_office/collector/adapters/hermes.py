from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from agent_office.models import Capability, EventRecord, EventType, RuntimeType


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
