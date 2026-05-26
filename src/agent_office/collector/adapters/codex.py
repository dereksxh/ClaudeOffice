from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from agent_office.collector.adapters.base import AdapterCommandResult
from agent_office.collector.adapters.files import append_command_outbox, parse_timestamp, read_jsonl_records, record_payload
from agent_office.models import Capability, EventRecord, EventType, RuntimeType
from agent_office.models import ControlCommand


CODEX_CAPABILITIES = [
    Capability.APPEND_PROMPT.value,
    Capability.REQUEST_REPORT.value,
    Capability.CONTINUE.value,
]


def _text_from_content(content: object) -> str | None:
    if isinstance(content, str):
        return content.strip() or None
    if not isinstance(content, list):
        return None

    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            parts.append(text.strip())
    if not parts:
        return None
    return "\n".join(parts)


def _short_text(value: str | None, limit: int = 180) -> str | None:
    if value is None:
        return None
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "..."


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


class CodexHookLogAdapter:
    runtime_type = RuntimeType.CODEX

    def __init__(
        self,
        machine_id: str,
        hook_log_path: str | Path,
        command_outbox_path: str | Path | None = None,
    ) -> None:
        self.machine_id = machine_id
        self.hook_log_path = Path(hook_log_path)
        self.command_outbox_path = Path(command_outbox_path) if command_outbox_path else None

    def snapshot_events(self, now: datetime) -> list[EventRecord]:
        events: list[EventRecord] = []
        for record in read_jsonl_records(self.hook_log_path):
            hook_event_name = record.get("hook_event_name") or record.get("event_name") or record.get("event")
            if not isinstance(hook_event_name, str) or not hook_event_name:
                continue
            events.append(
                map_codex_hook_event(
                    machine_id=self.machine_id,
                    hook_event_name=hook_event_name,
                    payload=record_payload(record),
                    timestamp=parse_timestamp(record.get("timestamp"), now),
                )
            )
        return events

    def apply_command(self, command: ControlCommand) -> AdapterCommandResult:
        if command.target_machine_id != self.machine_id:
            return AdapterCommandResult(False, "command targets a different machine")
        if self.command_outbox_path is None:
            return AdapterCommandResult(False, "codex command outbox is not configured")
        append_command_outbox(self.command_outbox_path, self.runtime_type, command)
        return AdapterCommandResult(True, f"{command.action.value} written to Codex command outbox")


class CodexSessionDirectoryAdapter:
    runtime_type = RuntimeType.CODEX

    def __init__(
        self,
        machine_id: str,
        sessions_dir: str | Path,
        max_sessions: int = 20,
        active_ttl_seconds: int = 600,
    ) -> None:
        self.machine_id = machine_id
        self.sessions_dir = Path(sessions_dir)
        self.max_sessions = max_sessions
        self.active_ttl_seconds = active_ttl_seconds

    def snapshot_events(self, now: datetime) -> list[EventRecord]:
        if not self.sessions_dir.exists():
            return []

        files = sorted(
            self.sessions_dir.glob("**/*.jsonl"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )[: self.max_sessions]
        return [event for event in (self._event_from_session_file(path, now) for path in files) if event is not None]

    def apply_command(self, command: ControlCommand) -> AdapterCommandResult:
        return AdapterCommandResult(False, "codex session directory adapter is read-only")

    def _event_from_session_file(self, path: Path, now: datetime) -> EventRecord | None:
        session_id = path.stem
        cwd: str | None = None
        model: str | None = None
        current_task: str | None = None
        progress_summary: str | None = None
        latest_timestamp = datetime.fromtimestamp(path.stat().st_mtime, tz=now.tzinfo)

        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            latest_timestamp = parse_timestamp(record.get("timestamp"), latest_timestamp)
            payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}

            if record.get("type") == "session_meta":
                meta = payload
                session_id = str(meta.get("id") or session_id)
                cwd = meta.get("cwd") if isinstance(meta.get("cwd"), str) else cwd
                model = meta.get("model") if isinstance(meta.get("model"), str) else model
            elif payload.get("type") == "message":
                role = payload.get("role")
                text = _short_text(_text_from_content(payload.get("content")))
                if role == "user" and text:
                    current_task = text
                elif role == "assistant" and text:
                    progress_summary = text
            elif record.get("type") == "event_msg":
                event_type = payload.get("type")
                if isinstance(event_type, str):
                    progress_summary = event_type.replace("_", " ")

        project_name = Path(cwd).name if cwd else path.parent.name
        status = "working" if (now - latest_timestamp).total_seconds() <= self.active_ttl_seconds else "idle"
        stat = path.stat()
        raw = f"{self.machine_id}:{session_id}:{path}:{stat.st_mtime_ns}:{stat.st_size}:{now.isoformat()}"
        return EventRecord(
            event_id="codex-session-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24],
            machine_id=self.machine_id,
            runtime_type=RuntimeType.CODEX,
            session_id=session_id,
            agent_id="main",
            event_type=EventType.SESSION_UPDATED,
            timestamp=now,
            payload={
                "cwd": cwd,
                "project_name": project_name,
                "model": model,
                "current_task": current_task,
                "progress_summary": progress_summary,
                "status": status,
                "capabilities": [],
            },
            source_ref=str(path),
        )
