from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class RuntimeType(StrEnum):
    CODEX = "codex"
    CLAUDE_CODE = "claude_code"
    HERMES = "hermes"


class SessionStatus(StrEnum):
    STARTING = "starting"
    IDLE = "idle"
    WORKING = "working"
    WAITING_INPUT = "waiting_input"
    WAITING_PERMISSION = "waiting_permission"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    LOST = "lost"


class Capability(StrEnum):
    APPEND_PROMPT = "append_prompt"
    REQUEST_REPORT = "request_report"
    CONTINUE = "continue"


class EventType(StrEnum):
    MACHINE_HEARTBEAT = "machine_heartbeat"
    SESSION_STARTED = "session_started"
    SESSION_UPDATED = "session_updated"
    SESSION_STOPPED = "session_stopped"
    AGENT_STARTED = "agent_started"
    AGENT_UPDATED = "agent_updated"
    AGENT_STOPPED = "agent_stopped"
    TOOL_STARTED = "tool_started"
    TOOL_FINISHED = "tool_finished"
    USER_PROMPT = "user_prompt"
    WAITING_PERMISSION = "waiting_permission"
    COMMAND_RESULT = "command_result"
    ERROR = "error"


class CommandAction(StrEnum):
    APPEND_PROMPT = "append_prompt"
    REQUEST_REPORT = "request_report"
    CONTINUE = "continue"


class CommandStatus(StrEnum):
    QUEUED = "queued"
    LEASED = "leased"
    APPLIED = "applied"
    FAILED = "failed"
    EXPIRED = "expired"


class Machine(BaseModel):
    machine_id: str
    hostname: str
    labels: dict[str, str] = Field(default_factory=dict)
    collector_version: str | None = None
    last_heartbeat_at: datetime | None = None
    health: str = "unknown"
    runtime_inventory: list[RuntimeType] = Field(default_factory=list)


class RuntimeSession(BaseModel):
    session_id: str
    machine_id: str
    runtime_type: RuntimeType
    status: SessionStatus
    cwd: str | None = None
    project_name: str | None = None
    model: str | None = None
    current_task: str | None = None
    progress_summary: str | None = None
    last_event_at: datetime | None = None
    capabilities: list[Capability] = Field(default_factory=list)
    source_ref: str | None = None


class AgentInstance(BaseModel):
    agent_id: str
    machine_id: str
    session_id: str
    parent_agent_id: str | None = None
    native_agent_id: str | None = None
    agent_type: str | None = None
    status: SessionStatus = SessionStatus.STARTING
    task_description: str | None = None
    progress_summary: str | None = None
    capabilities: list[Capability] = Field(default_factory=list)


class EventRecord(BaseModel):
    event_id: str
    machine_id: str
    runtime_type: RuntimeType
    session_id: str | None = None
    agent_id: str | None = None
    event_type: EventType
    timestamp: datetime = Field(default_factory=utc_now)
    payload: dict[str, Any] = Field(default_factory=dict)
    source_ref: str | None = None


class ControlCommand(BaseModel):
    command_id: str
    target_machine_id: str
    target_session_id: str
    target_agent_id: str | None = None
    action: CommandAction
    payload: dict[str, Any] = Field(default_factory=dict)
    actor: str
    status: CommandStatus = CommandStatus.QUEUED
    created_at: datetime = Field(default_factory=utc_now)
    leased_at: datetime | None = None
    completed_at: datetime | None = None
    result_summary: str | None = None
    audit_metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectedState(BaseModel):
    machines: list[Machine] = Field(default_factory=list)
    sessions: list[RuntimeSession] = Field(default_factory=list)
    agents: list[AgentInstance] = Field(default_factory=list)
    commands: list[ControlCommand] = Field(default_factory=list)
