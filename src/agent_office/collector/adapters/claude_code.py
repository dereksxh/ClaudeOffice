from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

from agent_office.models import Capability, EventRecord, EventType, RuntimeType


CLAUDE_CAPABILITIES = [
    Capability.APPEND_PROMPT.value,
    Capability.REQUEST_REPORT.value,
    Capability.CONTINUE.value,
]


def _event_id(machine_id: str, session_id: str, hook_event_name: str, payload: dict[str, Any]) -> str:
    raw = f"{machine_id}:{session_id}:{hook_event_name}:{payload.get('tool_use_id')}:{payload.get('agent_id')}"
    return "claude-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def map_claude_hook_event(
    machine_id: str,
    hook_event_name: str,
    payload: dict[str, Any],
    timestamp: datetime,
) -> EventRecord:
    session_id = str(payload.get("session_id") or "unknown")
    cwd = payload.get("cwd")
    project_name = Path(cwd).name if isinstance(cwd, str) and cwd else None
    tool_name = payload.get("tool_name")
    tool_use_id = str(payload.get("tool_use_id") or "unknown")

    event_type = EventType.SESSION_UPDATED
    agent_id = payload.get("agent_id") or "main"
    event_payload: dict[str, Any] = {
        "cwd": cwd,
        "project_name": project_name,
        "capabilities": CLAUDE_CAPABILITIES,
    }

    if hook_event_name == "session_start":
        event_type = EventType.SESSION_STARTED
    elif hook_event_name == "user_prompt_submit":
        event_type = EventType.USER_PROMPT
        event_payload["current_task"] = payload.get("prompt")
    elif hook_event_name == "pre_tool_use" and tool_name in {"Task", "Agent"}:
        tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
        event_type = EventType.AGENT_STARTED
        agent_id = f"subagent_{tool_use_id}"
        event_payload.update(
            {
                "agent_type": tool_input.get("subagent_type"),
                "task_description": tool_input.get("prompt") or tool_input.get("description"),
            }
        )
    elif hook_event_name == "pre_tool_use":
        event_type = EventType.TOOL_STARTED
        event_payload["tool_name"] = tool_name
    elif hook_event_name == "post_tool_use":
        event_type = EventType.TOOL_FINISHED
        event_payload["tool_name"] = tool_name
    elif hook_event_name == "subagent_start":
        event_type = EventType.AGENT_STARTED
        agent_id = str(payload.get("agent_id") or agent_id)
        event_payload["native_agent_id"] = payload.get("agent_id")
    elif hook_event_name == "subagent_stop":
        event_type = EventType.AGENT_STOPPED
        agent_id = str(payload.get("agent_id") or agent_id)
    elif hook_event_name == "stop":
        event_type = EventType.SESSION_STOPPED

    return EventRecord(
        event_id=_event_id(machine_id, session_id, hook_event_name, payload),
        machine_id=machine_id,
        runtime_type=RuntimeType.CLAUDE_CODE,
        session_id=session_id,
        agent_id=agent_id,
        event_type=event_type,
        timestamp=timestamp,
        payload=event_payload,
        source_ref=f"claude_code:{hook_event_name}",
    )
