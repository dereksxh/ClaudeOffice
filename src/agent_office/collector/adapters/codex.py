from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

from agent_office.models import Capability, EventRecord, EventType, RuntimeType


CODEX_CAPABILITIES = [
    Capability.APPEND_PROMPT.value,
    Capability.REQUEST_REPORT.value,
    Capability.CONTINUE.value,
]


def _event_id(machine_id: str, session_id: str, hook_event_name: str, payload: dict[str, Any]) -> str:
    tool_id = payload.get("tool_use_id") or payload.get("tool_call_id")
    raw = f"{machine_id}:{session_id}:{hook_event_name}:{payload.get('turn_id')}:{tool_id}:{payload.get('prompt')}"
    return "codex-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def map_codex_hook_event(
    machine_id: str,
    hook_event_name: str,
    payload: dict[str, Any],
    timestamp: datetime,
) -> EventRecord:
    session_id = str(payload.get("session_id") or "unknown")
    cwd = payload.get("cwd")
    project_name = Path(cwd).name if isinstance(cwd, str) and cwd else None

    event_type = EventType.SESSION_UPDATED
    event_payload: dict[str, Any] = {
        "cwd": cwd,
        "project_name": project_name,
        "model": payload.get("model"),
        "capabilities": CODEX_CAPABILITIES,
    }

    if hook_event_name == "SessionStart":
        event_type = EventType.SESSION_STARTED
    elif hook_event_name == "UserPromptSubmit":
        event_type = EventType.USER_PROMPT
        event_payload["current_task"] = payload.get("prompt")
        event_payload["progress_summary"] = "User prompt submitted"
    elif hook_event_name == "PreToolUse":
        event_type = EventType.TOOL_STARTED
        event_payload["tool_name"] = payload.get("tool_name") or payload.get("tool")
    elif hook_event_name == "PostToolUse":
        event_type = EventType.TOOL_FINISHED
        event_payload["tool_name"] = payload.get("tool_name") or payload.get("tool")
    elif hook_event_name == "SubagentStart":
        event_type = EventType.AGENT_STARTED
    elif hook_event_name == "SubagentStop":
        event_type = EventType.AGENT_STOPPED
    elif hook_event_name == "Stop":
        event_type = EventType.SESSION_STOPPED

    return EventRecord(
        event_id=_event_id(machine_id, session_id, hook_event_name, payload),
        machine_id=machine_id,
        runtime_type=RuntimeType.CODEX,
        session_id=session_id,
        agent_id=payload.get("agent_id") or "main",
        event_type=event_type,
        timestamp=timestamp,
        payload=event_payload,
        source_ref=f"codex:{hook_event_name}",
    )
