# Agent Office Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Agent Office MVP: a central agent operations console, machine collector, runtime adapters, safe control command queue, live web UI, and simple Office/Building projection.

**Architecture:** Use a Python FastAPI central service with SQLite storage and WebSocket updates. Use a Python collector process with runtime adapters for Codex CLI, Claude Code, and Hermes/self-hosted agents. Serve a dense static web console from the same backend first; keep the Office/Building view as a projection of the same state.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, Pydantic v2, SQLite, pytest, httpx/FastAPI TestClient, vanilla HTML/CSS/JavaScript.

---

## File Structure

- `pyproject.toml` - package metadata, dependencies, pytest config, console scripts.
- `README.md` - local setup, running central, running collector, and MVP behavior.
- `src/agent_office/__init__.py` - package version.
- `src/agent_office/models.py` - shared enums and Pydantic models for machines, sessions, agents, events, commands, and projected state.
- `src/agent_office/storage.py` - SQLite schema and repository functions.
- `src/agent_office/projector.py` - deterministic state projection from append-only events and command rows.
- `src/agent_office/server.py` - FastAPI app, API routes, static UI serving, WebSocket manager.
- `src/agent_office/collector/__init__.py` - collector package marker.
- `src/agent_office/collector/adapters/base.py` - adapter protocol and command result model.
- `src/agent_office/collector/adapters/fake.py` - fake adapter for local integration tests.
- `src/agent_office/collector/adapters/codex.py` - Codex hook payload normalization and capability declaration.
- `src/agent_office/collector/adapters/claude_code.py` - Claude Code hook payload normalization and capability declaration.
- `src/agent_office/collector/adapters/hermes.py` - Hermes process/API/log snapshot normalization and capability declaration.
- `src/agent_office/collector/client.py` - central API client for heartbeat, event batches, command leasing, and command results.
- `src/agent_office/collector/runner.py` - collector loop wiring adapters to central.
- `src/agent_office/web/index.html` - static console shell.
- `src/agent_office/web/app.js` - frontend state fetching, WebSocket handling, table/detail rendering, and action drawer.
- `src/agent_office/web/styles.css` - dense control-console styling plus simple Office view styling.
- `tests/` - behavior tests mirroring the files above.

---

### Task 1: Project Scaffold And Shared Models

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `src/agent_office/__init__.py`
- Create: `src/agent_office/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Create package configuration**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "agent-office"
version = "0.1.0"
description = "Operations console for Codex, Claude Code, and Hermes agents"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115,<0.116",
  "uvicorn[standard]>=0.34,<0.35",
  "pydantic>=2.10,<3",
  "httpx>=0.28,<0.29",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3,<9",
  "pytest-asyncio>=0.25,<0.26",
]

[project.scripts]
agent-office-server = "agent_office.server:main"
agent-office-collector = "agent_office.collector.runner:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
addopts = "-q"
```

Create `README.md`:

```markdown
# Agent Office

Agent Office is an internal operations console for Codex CLI, Claude Code, and Hermes/self-hosted agents.

MVP capabilities:

- central event ingestion and projected state
- machine collector with runtime adapters
- safe control commands: append prompt, request report, continue
- dense console UI and simple Office/Building projection

Run tests:

```bash
python -m pytest
```

Run central locally:

```bash
AGENT_OFFICE_TOKEN=dev-token agent-office-server --host 0.0.0.0 --port 8080
```
```

Create `src/agent_office/__init__.py`:

```python
"""Agent Office package."""

__version__ = "0.1.0"
```

- [ ] **Step 2: Write failing model tests**

Create `tests/test_models.py`:

```python
from datetime import UTC, datetime

from pydantic import ValidationError

from agent_office.models import (
    Capability,
    CommandAction,
    CommandStatus,
    ControlCommand,
    EventRecord,
    EventType,
    Machine,
    RuntimeSession,
    RuntimeType,
    SessionStatus,
)


def test_runtime_session_requires_standard_status_and_runtime_type() -> None:
    session = RuntimeSession(
        session_id="codex-1",
        machine_id="machine-a",
        runtime_type=RuntimeType.CODEX,
        status=SessionStatus.WORKING,
        cwd="/work/repo",
        project_name="repo",
        model="gpt-5",
        current_task="Build tests",
        progress_summary="running pytest",
        capabilities=[Capability.APPEND_PROMPT, Capability.REQUEST_REPORT],
        last_event_at=datetime(2026, 5, 26, 3, 0, tzinfo=UTC),
    )

    assert session.runtime_type == RuntimeType.CODEX
    assert session.status == SessionStatus.WORKING
    assert Capability.APPEND_PROMPT in session.capabilities


def test_event_record_accepts_append_only_payload() -> None:
    event = EventRecord(
        event_id="evt-1",
        machine_id="machine-a",
        runtime_type=RuntimeType.CLAUDE_CODE,
        session_id="claude-1",
        agent_id="main",
        event_type=EventType.TOOL_STARTED,
        timestamp=datetime(2026, 5, 26, 3, 1, tzinfo=UTC),
        payload={"tool_name": "Bash"},
        source_ref="hook:post-tool",
    )

    assert event.payload["tool_name"] == "Bash"
    assert event.source_ref == "hook:post-tool"


def test_control_command_tracks_audited_safe_action() -> None:
    command = ControlCommand(
        command_id="cmd-1",
        target_machine_id="machine-a",
        target_session_id="codex-1",
        target_agent_id="main",
        action=CommandAction.REQUEST_REPORT,
        payload={"prompt": "Please summarize progress and blockers."},
        actor="derek",
        status=CommandStatus.QUEUED,
        created_at=datetime(2026, 5, 26, 3, 2, tzinfo=UTC),
        audit_metadata={"source": "web-ui"},
    )

    assert command.action == CommandAction.REQUEST_REPORT
    assert command.status == CommandStatus.QUEUED
    assert command.audit_metadata["source"] == "web-ui"


def test_machine_health_defaults_to_unknown() -> None:
    machine = Machine(machine_id="machine-a", hostname="worker-a")

    assert machine.health == "unknown"
    assert machine.labels == {}


def test_rejects_unsupported_runtime_type() -> None:
    try:
        RuntimeSession(
            session_id="bad-1",
            machine_id="machine-a",
            runtime_type="unknown-runtime",
            status=SessionStatus.IDLE,
        )
    except ValidationError as exc:
        assert "runtime_type" in str(exc)
    else:
        raise AssertionError("invalid runtime_type should fail validation")
```

- [ ] **Step 3: Run model tests to verify RED**

Run:

```bash
python -m pytest tests/test_models.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'agent_office.models'`.

- [ ] **Step 4: Implement shared models**

Create `src/agent_office/models.py`:

```python
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
```

- [ ] **Step 5: Run model tests to verify GREEN**

Run:

```bash
python -m pytest tests/test_models.py -q
```

Expected: PASS, `5 passed`.

- [ ] **Step 6: Commit model scaffold**

```bash
git add pyproject.toml README.md src/agent_office/__init__.py src/agent_office/models.py tests/test_models.py
git commit -m "feat: add Agent Office shared models"
```

---

### Task 2: SQLite Storage And Command Queue

**Files:**
- Create: `src/agent_office/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write failing storage tests**

Create `tests/test_storage.py`:

```python
import sqlite3
from datetime import UTC, datetime, timedelta

from agent_office.models import (
    CommandAction,
    CommandStatus,
    ControlCommand,
    EventRecord,
    EventType,
    RuntimeType,
)
from agent_office.storage import (
    complete_command,
    create_command,
    init_db,
    insert_event,
    lease_commands,
    list_commands,
    list_events,
)


def make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def test_insert_event_is_idempotent_by_event_id() -> None:
    conn = make_conn()
    event = EventRecord(
        event_id="evt-1",
        machine_id="machine-a",
        runtime_type=RuntimeType.CODEX,
        session_id="codex-1",
        event_type=EventType.SESSION_STARTED,
        timestamp=datetime(2026, 5, 26, 3, 0, tzinfo=UTC),
        payload={"cwd": "/repo"},
    )

    assert insert_event(conn, event) is True
    assert insert_event(conn, event) is False

    events = list_events(conn)
    assert len(events) == 1
    assert events[0].event_id == "evt-1"


def test_command_can_be_created_leased_and_completed() -> None:
    conn = make_conn()
    command = ControlCommand(
        command_id="cmd-1",
        target_machine_id="machine-a",
        target_session_id="codex-1",
        action=CommandAction.REQUEST_REPORT,
        payload={"prompt": "Report progress."},
        actor="derek",
        created_at=datetime(2026, 5, 26, 3, 0, tzinfo=UTC),
    )
    create_command(conn, command)

    leased = lease_commands(
        conn,
        machine_id="machine-a",
        now=datetime(2026, 5, 26, 3, 1, tzinfo=UTC),
        limit=5,
    )

    assert [cmd.command_id for cmd in leased] == ["cmd-1"]
    assert leased[0].status == CommandStatus.LEASED

    complete_command(
        conn,
        command_id="cmd-1",
        status=CommandStatus.APPLIED,
        result_summary="report requested",
        completed_at=datetime(2026, 5, 26, 3, 2, tzinfo=UTC),
    )

    commands = list_commands(conn)
    assert commands[0].status == CommandStatus.APPLIED
    assert commands[0].result_summary == "report requested"


def test_lease_ignores_commands_for_other_machines() -> None:
    conn = make_conn()
    create_command(
        conn,
        ControlCommand(
            command_id="cmd-1",
            target_machine_id="machine-b",
            target_session_id="claude-1",
            action=CommandAction.CONTINUE,
            actor="derek",
        ),
    )

    leased = lease_commands(
        conn,
        machine_id="machine-a",
        now=datetime(2026, 5, 26, 3, 1, tzinfo=UTC),
        limit=5,
    )

    assert leased == []


def test_expired_leased_command_can_be_released() -> None:
    conn = make_conn()
    create_command(
        conn,
        ControlCommand(
            command_id="cmd-1",
            target_machine_id="machine-a",
            target_session_id="codex-1",
            action=CommandAction.CONTINUE,
            actor="derek",
        ),
    )
    first_lease = lease_commands(
        conn,
        machine_id="machine-a",
        now=datetime(2026, 5, 26, 3, 0, tzinfo=UTC),
        limit=5,
    )
    assert len(first_lease) == 1

    second_lease = lease_commands(
        conn,
        machine_id="machine-a",
        now=datetime(2026, 5, 26, 3, 10, tzinfo=UTC),
        limit=5,
        lease_ttl=timedelta(minutes=5),
    )

    assert len(second_lease) == 1
    assert second_lease[0].command_id == "cmd-1"
```

- [ ] **Step 2: Run storage tests to verify RED**

Run:

```bash
python -m pytest tests/test_storage.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'agent_office.storage'`.

- [ ] **Step 3: Implement storage module**

Create `src/agent_office/storage.py`:

```python
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta

from agent_office.models import CommandStatus, ControlCommand, EventRecord


def _dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            machine_id TEXT NOT NULL,
            runtime_type TEXT NOT NULL,
            session_id TEXT,
            agent_id TEXT,
            event_type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            source_ref TEXT
        );

        CREATE TABLE IF NOT EXISTS commands (
            command_id TEXT PRIMARY KEY,
            target_machine_id TEXT NOT NULL,
            target_session_id TEXT NOT NULL,
            target_agent_id TEXT,
            action TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            actor TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            leased_at TEXT,
            completed_at TEXT,
            result_summary TEXT,
            audit_metadata_json TEXT NOT NULL
        );
        """
    )
    conn.commit()


def insert_event(conn: sqlite3.Connection, event: EventRecord) -> bool:
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO events (
            event_id, machine_id, runtime_type, session_id, agent_id,
            event_type, timestamp, payload_json, source_ref
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.event_id,
            event.machine_id,
            event.runtime_type.value,
            event.session_id,
            event.agent_id,
            event.event_type.value,
            _dt(event.timestamp),
            json.dumps(event.payload, sort_keys=True),
            event.source_ref,
        ),
    )
    conn.commit()
    return cursor.rowcount == 1


def list_events(conn: sqlite3.Connection) -> list[EventRecord]:
    rows = conn.execute("SELECT * FROM events ORDER BY timestamp, event_id").fetchall()
    return [
        EventRecord(
            event_id=row["event_id"],
            machine_id=row["machine_id"],
            runtime_type=row["runtime_type"],
            session_id=row["session_id"],
            agent_id=row["agent_id"],
            event_type=row["event_type"],
            timestamp=_parse_dt(row["timestamp"]) or datetime.now(UTC),
            payload=json.loads(row["payload_json"]),
            source_ref=row["source_ref"],
        )
        for row in rows
    ]


def create_command(conn: sqlite3.Connection, command: ControlCommand) -> None:
    conn.execute(
        """
        INSERT INTO commands (
            command_id, target_machine_id, target_session_id, target_agent_id,
            action, payload_json, actor, status, created_at, leased_at,
            completed_at, result_summary, audit_metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            command.command_id,
            command.target_machine_id,
            command.target_session_id,
            command.target_agent_id,
            command.action.value,
            json.dumps(command.payload, sort_keys=True),
            command.actor,
            command.status.value,
            _dt(command.created_at),
            _dt(command.leased_at),
            _dt(command.completed_at),
            command.result_summary,
            json.dumps(command.audit_metadata, sort_keys=True),
        ),
    )
    conn.commit()


def _row_to_command(row: sqlite3.Row) -> ControlCommand:
    return ControlCommand(
        command_id=row["command_id"],
        target_machine_id=row["target_machine_id"],
        target_session_id=row["target_session_id"],
        target_agent_id=row["target_agent_id"],
        action=row["action"],
        payload=json.loads(row["payload_json"]),
        actor=row["actor"],
        status=row["status"],
        created_at=_parse_dt(row["created_at"]) or datetime.now(UTC),
        leased_at=_parse_dt(row["leased_at"]),
        completed_at=_parse_dt(row["completed_at"]),
        result_summary=row["result_summary"],
        audit_metadata=json.loads(row["audit_metadata_json"]),
    )


def list_commands(conn: sqlite3.Connection) -> list[ControlCommand]:
    rows = conn.execute("SELECT * FROM commands ORDER BY created_at, command_id").fetchall()
    return [_row_to_command(row) for row in rows]


def lease_commands(
    conn: sqlite3.Connection,
    machine_id: str,
    now: datetime,
    limit: int,
    lease_ttl: timedelta = timedelta(minutes=5),
) -> list[ControlCommand]:
    cutoff = now - lease_ttl
    rows = conn.execute(
        """
        SELECT * FROM commands
        WHERE target_machine_id = ?
          AND (
            status = ?
            OR (status = ? AND leased_at < ?)
          )
        ORDER BY created_at, command_id
        LIMIT ?
        """,
        (
            machine_id,
            CommandStatus.QUEUED.value,
            CommandStatus.LEASED.value,
            _dt(cutoff),
            limit,
        ),
    ).fetchall()

    command_ids = [row["command_id"] for row in rows]
    if command_ids:
        conn.executemany(
            "UPDATE commands SET status = ?, leased_at = ? WHERE command_id = ?",
            [(CommandStatus.LEASED.value, _dt(now), command_id) for command_id in command_ids],
        )
        conn.commit()

    refreshed = [
        conn.execute("SELECT * FROM commands WHERE command_id = ?", (command_id,)).fetchone()
        for command_id in command_ids
    ]
    return [_row_to_command(row) for row in refreshed if row is not None]


def complete_command(
    conn: sqlite3.Connection,
    command_id: str,
    status: CommandStatus,
    result_summary: str,
    completed_at: datetime,
) -> None:
    conn.execute(
        """
        UPDATE commands
        SET status = ?, result_summary = ?, completed_at = ?
        WHERE command_id = ?
        """,
        (status.value, result_summary, _dt(completed_at), command_id),
    )
    conn.commit()
```

- [ ] **Step 4: Run storage tests to verify GREEN**

Run:

```bash
python -m pytest tests/test_storage.py -q
```

Expected: PASS, `4 passed`.

- [ ] **Step 5: Run model and storage tests**

Run:

```bash
python -m pytest tests/test_models.py tests/test_storage.py -q
```

Expected: PASS, `9 passed`.

- [ ] **Step 6: Commit storage**

```bash
git add src/agent_office/storage.py tests/test_storage.py
git commit -m "feat: add event storage and command queue"
```

---

### Task 3: Deterministic State Projector

**Files:**
- Create: `src/agent_office/projector.py`
- Test: `tests/test_projector.py`

- [ ] **Step 1: Write failing projector tests**

Create `tests/test_projector.py`:

```python
from datetime import UTC, datetime, timedelta

from agent_office.models import (
    Capability,
    CommandAction,
    ControlCommand,
    EventRecord,
    EventType,
    RuntimeType,
    SessionStatus,
)
from agent_office.projector import project_state


def test_projector_builds_machine_and_session_from_events() -> None:
    events = [
        EventRecord(
            event_id="evt-heartbeat",
            machine_id="machine-a",
            runtime_type=RuntimeType.CODEX,
            event_type=EventType.MACHINE_HEARTBEAT,
            timestamp=datetime(2026, 5, 26, 3, 0, tzinfo=UTC),
            payload={
                "hostname": "worker-a",
                "labels": {"region": "sg"},
                "collector_version": "0.1.0",
                "runtime_inventory": ["codex", "claude_code"],
            },
        ),
        EventRecord(
            event_id="evt-session",
            machine_id="machine-a",
            runtime_type=RuntimeType.CODEX,
            session_id="codex-1",
            event_type=EventType.SESSION_STARTED,
            timestamp=datetime(2026, 5, 26, 3, 1, tzinfo=UTC),
            payload={
                "cwd": "/repo",
                "project_name": "repo",
                "model": "gpt-5",
                "current_task": "Build Agent Office",
                "capabilities": ["append_prompt", "request_report"],
            },
        ),
        EventRecord(
            event_id="evt-tool",
            machine_id="machine-a",
            runtime_type=RuntimeType.CODEX,
            session_id="codex-1",
            agent_id="main",
            event_type=EventType.TOOL_STARTED,
            timestamp=datetime(2026, 5, 26, 3, 2, tzinfo=UTC),
            payload={"tool_name": "Bash"},
        ),
    ]

    state = project_state(events, [], now=datetime(2026, 5, 26, 3, 3, tzinfo=UTC))

    assert state.machines[0].hostname == "worker-a"
    assert state.machines[0].runtime_inventory == [RuntimeType.CODEX, RuntimeType.CLAUDE_CODE]
    assert state.sessions[0].session_id == "codex-1"
    assert state.sessions[0].status == SessionStatus.WORKING
    assert state.sessions[0].progress_summary == "Running tool: Bash"
    assert Capability.APPEND_PROMPT in state.sessions[0].capabilities


def test_projector_marks_stale_machine_sessions_lost() -> None:
    events = [
        EventRecord(
            event_id="evt-heartbeat",
            machine_id="machine-a",
            runtime_type=RuntimeType.CLAUDE_CODE,
            event_type=EventType.MACHINE_HEARTBEAT,
            timestamp=datetime(2026, 5, 26, 3, 0, tzinfo=UTC),
            payload={"hostname": "worker-a"},
        ),
        EventRecord(
            event_id="evt-session",
            machine_id="machine-a",
            runtime_type=RuntimeType.CLAUDE_CODE,
            session_id="claude-1",
            event_type=EventType.SESSION_STARTED,
            timestamp=datetime(2026, 5, 26, 3, 1, tzinfo=UTC),
            payload={"project_name": "repo"},
        ),
    ]

    state = project_state(
        events,
        [],
        now=datetime(2026, 5, 26, 3, 20, tzinfo=UTC),
        heartbeat_timeout=timedelta(minutes=10),
    )

    assert state.machines[0].health == "lost"
    assert state.sessions[0].status == SessionStatus.LOST


def test_projector_includes_commands_in_state() -> None:
    command = ControlCommand(
        command_id="cmd-1",
        target_machine_id="machine-a",
        target_session_id="codex-1",
        action=CommandAction.CONTINUE,
        actor="derek",
        created_at=datetime(2026, 5, 26, 3, 0, tzinfo=UTC),
    )

    state = project_state([], [command], now=datetime(2026, 5, 26, 3, 1, tzinfo=UTC))

    assert state.commands == [command]
```

- [ ] **Step 2: Run projector tests to verify RED**

Run:

```bash
python -m pytest tests/test_projector.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'agent_office.projector'`.

- [ ] **Step 3: Implement projector**

Create `src/agent_office/projector.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from agent_office.models import (
    AgentInstance,
    Capability,
    ControlCommand,
    EventRecord,
    EventType,
    Machine,
    ProjectedState,
    RuntimeSession,
    RuntimeType,
    SessionStatus,
)


def _capabilities(values: list[str] | None) -> list[Capability]:
    result: list[Capability] = []
    for value in values or []:
        try:
            result.append(Capability(value))
        except ValueError:
            continue
    return result


def _runtime_inventory(values: list[str] | None) -> list[RuntimeType]:
    result: list[RuntimeType] = []
    for value in values or []:
        try:
            result.append(RuntimeType(value))
        except ValueError:
            continue
    return result


def project_state(
    events: list[EventRecord],
    commands: list[ControlCommand],
    now: datetime | None = None,
    heartbeat_timeout: timedelta = timedelta(minutes=5),
) -> ProjectedState:
    now = now or datetime.now(UTC)
    machines: dict[str, Machine] = {}
    sessions: dict[tuple[str, str], RuntimeSession] = {}
    agents: dict[tuple[str, str], AgentInstance] = {}

    for event in sorted(events, key=lambda item: (item.timestamp, item.event_id)):
        if event.event_type == EventType.MACHINE_HEARTBEAT:
            machines[event.machine_id] = Machine(
                machine_id=event.machine_id,
                hostname=str(event.payload.get("hostname") or event.machine_id),
                labels=dict(event.payload.get("labels") or {}),
                collector_version=event.payload.get("collector_version"),
                last_heartbeat_at=event.timestamp,
                health="online",
                runtime_inventory=_runtime_inventory(event.payload.get("runtime_inventory")),
            )
            continue

        if event.machine_id not in machines:
            machines[event.machine_id] = Machine(
                machine_id=event.machine_id,
                hostname=event.machine_id,
                last_heartbeat_at=event.timestamp,
                health="online",
            )

        if event.session_id:
            key = (event.machine_id, event.session_id)
            current = sessions.get(key)
            if current is None:
                current = RuntimeSession(
                    session_id=event.session_id,
                    machine_id=event.machine_id,
                    runtime_type=event.runtime_type,
                    status=SessionStatus.STARTING,
                    last_event_at=event.timestamp,
                )

            status = current.status
            progress_summary = current.progress_summary
            current_task = current.current_task

            if event.event_type == EventType.SESSION_STARTED:
                status = SessionStatus.WORKING
                current_task = event.payload.get("current_task") or current_task
                progress_summary = event.payload.get("progress_summary") or progress_summary
            elif event.event_type == EventType.SESSION_UPDATED:
                raw_status = event.payload.get("status")
                if raw_status:
                    status = SessionStatus(raw_status)
                progress_summary = event.payload.get("progress_summary") or progress_summary
                current_task = event.payload.get("current_task") or current_task
            elif event.event_type == EventType.TOOL_STARTED:
                status = SessionStatus.WORKING
                progress_summary = f"Running tool: {event.payload.get('tool_name', 'unknown')}"
            elif event.event_type == EventType.WAITING_PERMISSION:
                status = SessionStatus.WAITING_PERMISSION
                progress_summary = event.payload.get("message") or "Waiting for permission"
            elif event.event_type in {EventType.SESSION_STOPPED, EventType.AGENT_STOPPED}:
                status = SessionStatus.COMPLETED

            sessions[key] = RuntimeSession(
                session_id=current.session_id,
                machine_id=current.machine_id,
                runtime_type=current.runtime_type,
                status=status,
                cwd=event.payload.get("cwd") or current.cwd,
                project_name=event.payload.get("project_name") or current.project_name,
                model=event.payload.get("model") or current.model,
                current_task=current_task,
                progress_summary=progress_summary,
                last_event_at=event.timestamp,
                capabilities=_capabilities(event.payload.get("capabilities")) or current.capabilities,
                source_ref=event.source_ref or current.source_ref,
            )

        if event.session_id and event.agent_id:
            agent_key = (event.session_id, event.agent_id)
            existing = agents.get(agent_key)
            agents[agent_key] = AgentInstance(
                agent_id=event.agent_id,
                session_id=event.session_id,
                parent_agent_id=event.payload.get("parent_agent_id")
                or (existing.parent_agent_id if existing else None),
                native_agent_id=event.payload.get("native_agent_id")
                or (existing.native_agent_id if existing else None),
                agent_type=event.payload.get("agent_type") or (existing.agent_type if existing else None),
                status=sessions[(event.machine_id, event.session_id)].status,
                task_description=event.payload.get("task_description")
                or (existing.task_description if existing else None),
                progress_summary=sessions[(event.machine_id, event.session_id)].progress_summary,
                capabilities=sessions[(event.machine_id, event.session_id)].capabilities,
            )

    for machine_id, machine in list(machines.items()):
        if machine.last_heartbeat_at and now - machine.last_heartbeat_at > heartbeat_timeout:
            machines[machine_id] = machine.model_copy(update={"health": "lost"})
            for key, session in list(sessions.items()):
                if key[0] == machine_id:
                    sessions[key] = session.model_copy(update={"status": SessionStatus.LOST})

    return ProjectedState(
        machines=sorted(machines.values(), key=lambda item: item.machine_id),
        sessions=sorted(sessions.values(), key=lambda item: (item.machine_id, item.session_id)),
        agents=sorted(agents.values(), key=lambda item: (item.session_id, item.agent_id)),
        commands=sorted(commands, key=lambda item: (item.created_at, item.command_id)),
    )
```

- [ ] **Step 4: Run projector tests to verify GREEN**

Run:

```bash
python -m pytest tests/test_projector.py -q
```

Expected: PASS, `3 passed`.

- [ ] **Step 5: Run model, storage, projector tests**

Run:

```bash
python -m pytest tests/test_models.py tests/test_storage.py tests/test_projector.py -q
```

Expected: PASS, `12 passed`.

- [ ] **Step 6: Commit projector**

```bash
git add src/agent_office/projector.py tests/test_projector.py
git commit -m "feat: project agent office state from events"
```

---

### Task 4: Central FastAPI Service

**Files:**
- Create: `src/agent_office/server.py`
- Test: `tests/test_server.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/test_server.py`:

```python
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from agent_office.models import CommandAction, EventType, RuntimeType
from agent_office.server import create_app


def test_ingest_event_and_get_projected_state(tmp_path) -> None:
    app = create_app(db_path=tmp_path / "agent-office.sqlite", api_token="test-token")
    client = TestClient(app)

    response = client.post(
        "/api/events",
        headers={"Authorization": "Bearer test-token"},
        json={
            "event_id": "evt-1",
            "machine_id": "machine-a",
            "runtime_type": RuntimeType.CODEX,
            "session_id": "codex-1",
            "event_type": EventType.SESSION_STARTED,
            "timestamp": datetime(2026, 5, 26, 3, 0, tzinfo=UTC).isoformat(),
            "payload": {
                "project_name": "repo",
                "capabilities": ["request_report", "continue"],
            },
        },
    )

    assert response.status_code == 202

    state = client.get(
        "/api/state",
        headers={"Authorization": "Bearer test-token"},
    ).json()

    assert state["sessions"][0]["session_id"] == "codex-1"
    assert state["sessions"][0]["project_name"] == "repo"


def test_rejects_missing_token(tmp_path) -> None:
    app = create_app(db_path=tmp_path / "agent-office.sqlite", api_token="test-token")
    client = TestClient(app)

    response = client.get("/api/state")

    assert response.status_code == 401


def test_create_lease_and_complete_command(tmp_path) -> None:
    app = create_app(db_path=tmp_path / "agent-office.sqlite", api_token="test-token")
    client = TestClient(app)
    headers = {"Authorization": "Bearer test-token"}

    create_response = client.post(
        "/api/commands",
        headers=headers,
        json={
            "target_machine_id": "machine-a",
            "target_session_id": "codex-1",
            "action": CommandAction.REQUEST_REPORT,
            "payload": {"prompt": "Report progress."},
            "actor": "derek",
            "audit_metadata": {"source": "test"},
        },
    )

    assert create_response.status_code == 201
    command_id = create_response.json()["command_id"]

    lease_response = client.post(
        "/api/collector/commands/lease",
        headers=headers,
        json={"machine_id": "machine-a", "limit": 5},
    )
    assert lease_response.status_code == 200
    assert lease_response.json()["commands"][0]["command_id"] == command_id

    result_response = client.post(
        f"/api/collector/commands/{command_id}/result",
        headers=headers,
        json={"status": "applied", "result_summary": "report requested"},
    )
    assert result_response.status_code == 200

    state = client.get("/api/state", headers=headers).json()
    assert state["commands"][0]["status"] == "applied"


def test_static_index_is_served(tmp_path) -> None:
    app = create_app(db_path=tmp_path / "agent-office.sqlite", api_token="test-token")
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "Agent Office" in response.text
```

- [ ] **Step 2: Run API tests to verify RED**

Run:

```bash
python -m pytest tests/test_server.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'agent_office.server'`.

- [ ] **Step 3: Implement FastAPI app**

Create `src/agent_office/server.py`:

```python
from __future__ import annotations

import argparse
import os
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from agent_office.models import CommandStatus, ControlCommand, EventRecord, ProjectedState
from agent_office.projector import project_state
from agent_office.storage import (
    complete_command,
    create_command,
    init_db,
    insert_event,
    lease_commands,
    list_commands,
    list_events,
)

WEB_DIR = Path(__file__).parent / "web"


class CommandCreate(BaseModel):
    target_machine_id: str
    target_session_id: str
    target_agent_id: str | None = None
    action: str
    payload: dict = {}
    actor: str
    audit_metadata: dict = {}


class CommandLeaseRequest(BaseModel):
    machine_id: str
    limit: int = 10


class CommandLeaseResponse(BaseModel):
    commands: list[ControlCommand]


class CommandResult(BaseModel):
    status: CommandStatus
    result_summary: str


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self._connections:
            self._connections.remove(websocket)

    async def broadcast_state(self, state: ProjectedState) -> None:
        stale: list[WebSocket] = []
        payload = {"type": "state", "state": state.model_dump(mode="json")}
        for websocket in self._connections:
            try:
                await websocket.send_json(payload)
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            self.disconnect(websocket)


def create_app(db_path: str | Path, api_token: str) -> FastAPI:
    app = FastAPI(title="Agent Office")
    manager = ConnectionManager()

    def get_conn() -> sqlite3.Connection:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        init_db(conn)
        return conn

    def require_auth(authorization: Annotated[str | None, Header()] = None) -> None:
        expected = f"Bearer {api_token}"
        if authorization != expected:
            raise HTTPException(status_code=401, detail="Unauthorized")

    def current_state() -> ProjectedState:
        with get_conn() as conn:
            return project_state(list_events(conn), list_commands(conn))

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        path = WEB_DIR / "index.html"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return "<!doctype html><title>Agent Office</title><h1>Agent Office</h1>"

    @app.get("/app.js")
    def app_js() -> HTMLResponse:
        return HTMLResponse((WEB_DIR / "app.js").read_text(encoding="utf-8"), media_type="application/javascript")

    @app.get("/styles.css")
    def styles_css() -> HTMLResponse:
        return HTMLResponse((WEB_DIR / "styles.css").read_text(encoding="utf-8"), media_type="text/css")

    @app.post("/api/events", status_code=202)
    async def receive_event(event: EventRecord, _: None = Depends(require_auth)) -> dict[str, bool]:
        with get_conn() as conn:
            inserted = insert_event(conn, event)
            state = project_state(list_events(conn), list_commands(conn))
        await manager.broadcast_state(state)
        return {"inserted": inserted}

    @app.get("/api/state")
    def get_state(_: None = Depends(require_auth)) -> ProjectedState:
        return current_state()

    @app.post("/api/commands", status_code=201)
    async def post_command(payload: CommandCreate, _: None = Depends(require_auth)) -> ControlCommand:
        command = ControlCommand(
            command_id=f"cmd-{uuid.uuid4().hex}",
            target_machine_id=payload.target_machine_id,
            target_session_id=payload.target_session_id,
            target_agent_id=payload.target_agent_id,
            action=payload.action,
            payload=payload.payload,
            actor=payload.actor,
            audit_metadata=payload.audit_metadata,
        )
        with get_conn() as conn:
            create_command(conn, command)
            state = project_state(list_events(conn), list_commands(conn))
        await manager.broadcast_state(state)
        return command

    @app.post("/api/collector/commands/lease")
    def lease(payload: CommandLeaseRequest, _: None = Depends(require_auth)) -> CommandLeaseResponse:
        with get_conn() as conn:
            commands = lease_commands(conn, payload.machine_id, now=datetime.now(UTC), limit=payload.limit)
        return CommandLeaseResponse(commands=commands)

    @app.post("/api/collector/commands/{command_id}/result")
    async def command_result(
        command_id: str,
        payload: CommandResult,
        _: None = Depends(require_auth),
    ) -> dict[str, str]:
        with get_conn() as conn:
            complete_command(
                conn,
                command_id=command_id,
                status=payload.status,
                result_summary=payload.result_summary,
                completed_at=datetime.now(UTC),
            )
            state = project_state(list_events(conn), list_commands(conn))
        await manager.broadcast_state(state)
        return {"status": "accepted"}

    @app.websocket("/ws")
    async def websocket_state(websocket: WebSocket) -> None:
        await manager.connect(websocket)
        try:
            await websocket.send_json({"type": "state", "state": current_state().model_dump(mode="json")})
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket)

    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--db-path", default=os.environ.get("AGENT_OFFICE_DB", "agent-office.sqlite"))
    args = parser.parse_args()
    token = os.environ.get("AGENT_OFFICE_TOKEN", "dev-token")
    uvicorn.run(create_app(args.db_path, token), host=args.host, port=args.port)
```

- [ ] **Step 4: Add minimal static files for server test**

Create `src/agent_office/web/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Agent Office</title>
    <link rel="stylesheet" href="/styles.css">
  </head>
  <body>
    <main id="app">
      <h1>Agent Office</h1>
      <p>Loading agent state...</p>
    </main>
    <script src="/app.js"></script>
  </body>
</html>
```

Create `src/agent_office/web/app.js`:

```javascript
document.getElementById("app").dataset.agentOffice = "ready";
```

Create `src/agent_office/web/styles.css`:

```css
body {
  margin: 0;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: #f6f7f9;
  color: #1d2433;
}

main {
  padding: 24px;
}
```

- [ ] **Step 5: Run API tests to verify GREEN**

Run:

```bash
python -m pytest tests/test_server.py -q
```

Expected: PASS, `4 passed`.

- [ ] **Step 6: Run backend tests**

Run:

```bash
python -m pytest tests/test_models.py tests/test_storage.py tests/test_projector.py tests/test_server.py -q
```

Expected: PASS, `16 passed`.

- [ ] **Step 7: Commit central API**

```bash
git add src/agent_office/server.py src/agent_office/web/index.html src/agent_office/web/app.js src/agent_office/web/styles.css tests/test_server.py
git commit -m "feat: add central Agent Office API"
```

---

### Task 5: Collector Core With Fake Adapter

**Files:**
- Create: `src/agent_office/collector/__init__.py`
- Create: `src/agent_office/collector/adapters/base.py`
- Create: `src/agent_office/collector/adapters/fake.py`
- Create: `src/agent_office/collector/client.py`
- Create: `src/agent_office/collector/runner.py`
- Test: `tests/test_collector.py`

- [ ] **Step 1: Write failing collector tests**

Create `tests/test_collector.py`:

```python
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from agent_office.collector.adapters.fake import FakeAdapter
from agent_office.collector.client import CollectorClient
from agent_office.collector.runner import collect_once
from agent_office.models import CommandAction, EventType, RuntimeType
from agent_office.server import create_app


def test_fake_adapter_emits_heartbeat_and_session_event() -> None:
    adapter = FakeAdapter(machine_id="machine-a", hostname="worker-a")

    events = adapter.snapshot_events(now=datetime(2026, 5, 26, 3, 0, tzinfo=UTC))

    assert events[0].event_type == EventType.MACHINE_HEARTBEAT
    assert events[0].machine_id == "machine-a"
    assert events[1].runtime_type == RuntimeType.HERMES
    assert events[1].session_id == "fake-session"


def test_collector_posts_events_to_central(tmp_path) -> None:
    app = create_app(db_path=tmp_path / "agent-office.sqlite", api_token="test-token")
    test_client = TestClient(app)
    collector_client = CollectorClient.for_test_client(test_client, token="test-token")
    adapter = FakeAdapter(machine_id="machine-a", hostname="worker-a")

    collect_once(
        client=collector_client,
        adapters=[adapter],
        now=datetime(2026, 5, 26, 3, 0, tzinfo=UTC),
    )

    state = test_client.get(
        "/api/state",
        headers={"Authorization": "Bearer test-token"},
    ).json()
    assert state["machines"][0]["machine_id"] == "machine-a"
    assert state["sessions"][0]["session_id"] == "fake-session"


def test_collector_leases_and_applies_supported_command(tmp_path) -> None:
    app = create_app(db_path=tmp_path / "agent-office.sqlite", api_token="test-token")
    test_client = TestClient(app)
    collector_client = CollectorClient.for_test_client(test_client, token="test-token")
    adapter = FakeAdapter(machine_id="machine-a", hostname="worker-a")

    create_response = test_client.post(
        "/api/commands",
        headers={"Authorization": "Bearer test-token"},
        json={
            "target_machine_id": "machine-a",
            "target_session_id": "fake-session",
            "action": CommandAction.REQUEST_REPORT,
            "payload": {"prompt": "Report progress."},
            "actor": "derek",
        },
    )
    assert create_response.status_code == 201

    collect_once(
        client=collector_client,
        adapters=[adapter],
        now=datetime(2026, 5, 26, 3, 1, tzinfo=UTC),
    )

    state = test_client.get(
        "/api/state",
        headers={"Authorization": "Bearer test-token"},
    ).json()
    assert state["commands"][0]["status"] == "applied"
    assert adapter.applied_commands == ["request_report"]
```

- [ ] **Step 2: Run collector tests to verify RED**

Run:

```bash
python -m pytest tests/test_collector.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'agent_office.collector'`.

- [ ] **Step 3: Implement adapter base and fake adapter**

Create `src/agent_office/collector/__init__.py`:

```python
"""Machine collector package."""
```

Create `src/agent_office/collector/adapters/base.py`:

```python
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
```

Create `src/agent_office/collector/adapters/fake.py`:

```python
from __future__ import annotations

from datetime import datetime

from agent_office.collector.adapters.base import AdapterCommandResult
from agent_office.models import Capability, CommandAction, ControlCommand, EventRecord, EventType, RuntimeType


class FakeAdapter:
    def __init__(self, machine_id: str, hostname: str) -> None:
        self.machine_id = machine_id
        self.hostname = hostname
        self.applied_commands: list[str] = []

    def snapshot_events(self, now: datetime) -> list[EventRecord]:
        return [
            EventRecord(
                event_id=f"{self.machine_id}:heartbeat:{int(now.timestamp())}",
                machine_id=self.machine_id,
                runtime_type=RuntimeType.HERMES,
                event_type=EventType.MACHINE_HEARTBEAT,
                timestamp=now,
                payload={
                    "hostname": self.hostname,
                    "collector_version": "0.1.0",
                    "runtime_inventory": [RuntimeType.HERMES.value],
                },
                source_ref="fake:heartbeat",
            ),
            EventRecord(
                event_id=f"{self.machine_id}:fake-session:{int(now.timestamp())}",
                machine_id=self.machine_id,
                runtime_type=RuntimeType.HERMES,
                session_id="fake-session",
                agent_id="main",
                event_type=EventType.SESSION_STARTED,
                timestamp=now,
                payload={
                    "project_name": "fake-project",
                    "current_task": "Fake collector smoke",
                    "capabilities": [Capability.REQUEST_REPORT.value, Capability.CONTINUE.value],
                },
                source_ref="fake:session",
            ),
        ]

    def apply_command(self, command: ControlCommand) -> AdapterCommandResult:
        if command.action not in {CommandAction.REQUEST_REPORT, CommandAction.CONTINUE}:
            return AdapterCommandResult(False, f"unsupported action: {command.action.value}")
        self.applied_commands.append(command.action.value)
        return AdapterCommandResult(True, f"{command.action.value} applied to {command.target_session_id}")
```

- [ ] **Step 4: Implement collector client and runner**

Create `src/agent_office/collector/client.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

import httpx
from fastapi.testclient import TestClient

from agent_office.models import CommandStatus, ControlCommand, EventRecord


@dataclass
class CollectorClient:
    base_url: str
    token: str
    _test_client: TestClient | None = None

    @classmethod
    def for_test_client(cls, test_client: TestClient, token: str) -> "CollectorClient":
        return cls(base_url="http://testserver", token=token, _test_client=test_client)

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def post_event(self, event: EventRecord) -> None:
        payload = event.model_dump(mode="json")
        if self._test_client:
            response = self._test_client.post("/api/events", headers=self.headers, json=payload)
        else:
            response = httpx.post(f"{self.base_url}/api/events", headers=self.headers, json=payload, timeout=5)
        response.raise_for_status()

    def lease_commands(self, machine_id: str, limit: int = 10) -> list[ControlCommand]:
        payload = {"machine_id": machine_id, "limit": limit}
        if self._test_client:
            response = self._test_client.post("/api/collector/commands/lease", headers=self.headers, json=payload)
        else:
            response = httpx.post(
                f"{self.base_url}/api/collector/commands/lease",
                headers=self.headers,
                json=payload,
                timeout=5,
            )
        response.raise_for_status()
        return [ControlCommand(**item) for item in response.json()["commands"]]

    def post_command_result(self, command_id: str, status: CommandStatus, result_summary: str) -> None:
        payload = {"status": status.value, "result_summary": result_summary}
        if self._test_client:
            response = self._test_client.post(
                f"/api/collector/commands/{command_id}/result",
                headers=self.headers,
                json=payload,
            )
        else:
            response = httpx.post(
                f"{self.base_url}/api/collector/commands/{command_id}/result",
                headers=self.headers,
                json=payload,
                timeout=5,
            )
        response.raise_for_status()
```

Create `src/agent_office/collector/runner.py`:

```python
from __future__ import annotations

import argparse
import os
import time
from datetime import UTC, datetime

from agent_office.collector.adapters.base import RuntimeAdapter
from agent_office.collector.adapters.fake import FakeAdapter
from agent_office.collector.client import CollectorClient
from agent_office.models import CommandStatus


def collect_once(client: CollectorClient, adapters: list[RuntimeAdapter], now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    for adapter in adapters:
        for event in adapter.snapshot_events(now):
            client.post_event(event)

        commands = client.lease_commands(adapter.machine_id)
        for command in commands:
            result = adapter.apply_command(command)
            client.post_command_result(
                command.command_id,
                CommandStatus.APPLIED if result.applied else CommandStatus.FAILED,
                result.summary,
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--central-url", default=os.environ.get("AGENT_OFFICE_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--machine-id", default=os.uname().nodename)
    parser.add_argument("--hostname", default=os.uname().nodename)
    parser.add_argument("--interval", type=float, default=3.0)
    args = parser.parse_args()

    token = os.environ.get("AGENT_OFFICE_TOKEN", "dev-token")
    client = CollectorClient(base_url=args.central_url, token=token)
    adapters: list[RuntimeAdapter] = [FakeAdapter(machine_id=args.machine_id, hostname=args.hostname)]

    while True:
        collect_once(client, adapters)
        time.sleep(args.interval)
```

- [ ] **Step 5: Run collector tests to verify GREEN**

Run:

```bash
python -m pytest tests/test_collector.py -q
```

Expected: PASS, `3 passed`.

- [ ] **Step 6: Run all backend and collector tests**

Run:

```bash
python -m pytest tests/test_models.py tests/test_storage.py tests/test_projector.py tests/test_server.py tests/test_collector.py -q
```

Expected: PASS, `19 passed`.

- [ ] **Step 7: Commit collector core**

```bash
git add src/agent_office/collector tests/test_collector.py
git commit -m "feat: add collector core and fake adapter"
```

---

### Task 6: Codex, Claude Code, And Hermes Adapter Normalizers

**Files:**
- Create: `src/agent_office/collector/adapters/codex.py`
- Create: `src/agent_office/collector/adapters/claude_code.py`
- Create: `src/agent_office/collector/adapters/hermes.py`
- Test: `tests/test_runtime_adapters.py`

- [ ] **Step 1: Write failing adapter tests**

Create `tests/test_runtime_adapters.py`:

```python
from datetime import UTC, datetime

from agent_office.collector.adapters.claude_code import map_claude_hook_event
from agent_office.collector.adapters.codex import map_codex_hook_event
from agent_office.collector.adapters.hermes import map_hermes_snapshot
from agent_office.models import Capability, EventType, RuntimeType


def test_codex_user_prompt_maps_to_session_started_or_updated_event() -> None:
    event = map_codex_hook_event(
        machine_id="machine-a",
        hook_event_name="UserPromptSubmit",
        payload={
            "session_id": "codex-1",
            "cwd": "/repo",
            "model": "gpt-5",
            "prompt": "Build Agent Office",
        },
        timestamp=datetime(2026, 5, 26, 3, 0, tzinfo=UTC),
    )

    assert event.runtime_type == RuntimeType.CODEX
    assert event.event_type == EventType.USER_PROMPT
    assert event.session_id == "codex-1"
    assert event.payload["current_task"] == "Build Agent Office"
    assert Capability.REQUEST_REPORT.value in event.payload["capabilities"]


def test_claude_task_tool_maps_to_agent_started_event() -> None:
    event = map_claude_hook_event(
        machine_id="machine-a",
        hook_event_name="pre_tool_use",
        payload={
            "session_id": "claude-1",
            "tool_name": "Task",
            "tool_use_id": "tool-1",
            "cwd": "/repo",
            "tool_input": {
                "description": "Review storage",
                "prompt": "Review storage module",
                "subagent_type": "reviewer",
            },
        },
        timestamp=datetime(2026, 5, 26, 3, 0, tzinfo=UTC),
    )

    assert event.runtime_type == RuntimeType.CLAUDE_CODE
    assert event.event_type == EventType.AGENT_STARTED
    assert event.agent_id == "subagent_tool-1"
    assert event.payload["agent_type"] == "reviewer"
    assert event.payload["task_description"] == "Review storage module"


def test_hermes_snapshot_maps_to_session_update() -> None:
    event = map_hermes_snapshot(
        machine_id="machine-a",
        snapshot={
            "session_id": "hermes-1",
            "project_name": "ticketops",
            "status": "working",
            "summary": "processing gateway request",
            "can_accept_prompt": False,
        },
        timestamp=datetime(2026, 5, 26, 3, 0, tzinfo=UTC),
    )

    assert event.runtime_type == RuntimeType.HERMES
    assert event.event_type == EventType.SESSION_UPDATED
    assert event.payload["progress_summary"] == "processing gateway request"
    assert Capability.REQUEST_REPORT.value in event.payload["capabilities"]
    assert Capability.APPEND_PROMPT.value not in event.payload["capabilities"]
```

- [ ] **Step 2: Run adapter tests to verify RED**

Run:

```bash
python -m pytest tests/test_runtime_adapters.py -q
```

Expected: FAIL with `ModuleNotFoundError` for adapter modules.

- [ ] **Step 3: Implement Codex hook mapper**

Create `src/agent_office/collector/adapters/codex.py`:

```python
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
    raw = f"{machine_id}:{session_id}:{hook_event_name}:{payload.get('turn_id')}:{payload.get('tool_call_id')}:{payload.get('prompt')}"
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
```

- [ ] **Step 4: Implement Claude Code hook mapper**

Create `src/agent_office/collector/adapters/claude_code.py`:

```python
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
```

- [ ] **Step 5: Implement Hermes snapshot mapper**

Create `src/agent_office/collector/adapters/hermes.py`:

```python
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
```

- [ ] **Step 6: Run adapter tests to verify GREEN**

Run:

```bash
python -m pytest tests/test_runtime_adapters.py -q
```

Expected: PASS, `3 passed`.

- [ ] **Step 7: Run all tests**

Run:

```bash
python -m pytest -q
```

Expected: PASS, all current tests pass.

- [ ] **Step 8: Commit runtime adapters**

```bash
git add src/agent_office/collector/adapters/codex.py src/agent_office/collector/adapters/claude_code.py src/agent_office/collector/adapters/hermes.py tests/test_runtime_adapters.py
git commit -m "feat: add runtime adapter normalizers"
```

---

### Task 7: Dense Console UI And Capability-Gated Actions

**Files:**
- Modify: `src/agent_office/web/index.html`
- Modify: `src/agent_office/web/app.js`
- Modify: `src/agent_office/web/styles.css`
- Test: `tests/test_web_assets.py`

- [ ] **Step 1: Write failing web asset tests**

Create `tests/test_web_assets.py`:

```python
from pathlib import Path


WEB_DIR = Path("src/agent_office/web")


def test_web_app_contains_console_regions() -> None:
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")

    assert 'id="machine-list"' in html
    assert 'id="session-table"' in html
    assert 'id="session-detail"' in html
    assert 'id="office-view"' in html


def test_web_app_gates_actions_by_capability() -> None:
    js = (WEB_DIR / "app.js").read_text(encoding="utf-8")

    assert "renderActions" in js
    assert "append_prompt" in js
    assert "request_report" in js
    assert "continue" in js
    assert "session.capabilities.includes(action)" in js


def test_web_styles_keep_dense_console_layout() -> None:
    css = (WEB_DIR / "styles.css").read_text(encoding="utf-8")

    assert ".app-shell" in css
    assert ".session-table" in css
    assert ".office-grid" in css
```

- [ ] **Step 2: Run web asset tests to verify RED**

Run:

```bash
python -m pytest tests/test_web_assets.py -q
```

Expected: FAIL because current static files do not contain console regions or action gating.

- [ ] **Step 3: Replace static HTML shell**

Replace `src/agent_office/web/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Agent Office</title>
    <link rel="stylesheet" href="/styles.css">
  </head>
  <body>
    <div class="app-shell">
      <aside class="sidebar">
        <h1>Agent Office</h1>
        <p class="muted">Machines</p>
        <div id="machine-list" class="machine-list"></div>
      </aside>

      <main class="main-panel">
        <header class="toolbar">
          <div>
            <h2>Sessions</h2>
            <p class="muted">Codex, Claude Code, and Hermes activity</p>
          </div>
          <button id="refresh-button" type="button">Refresh</button>
        </header>

        <section class="console-grid">
          <div class="table-panel">
            <table class="session-table">
              <thead>
                <tr>
                  <th>Runtime</th>
                  <th>Project</th>
                  <th>Status</th>
                  <th>Machine</th>
                  <th>Progress</th>
                </tr>
              </thead>
              <tbody id="session-table"></tbody>
            </table>
          </div>

          <aside id="session-detail" class="detail-panel">
            <h3>Select a session</h3>
            <p class="muted">Details and actions appear here.</p>
          </aside>
        </section>

        <section>
          <h2>Office View</h2>
          <div id="office-view" class="office-grid"></div>
        </section>
      </main>
    </div>
    <script src="/app.js"></script>
  </body>
</html>
```

- [ ] **Step 4: Replace frontend JavaScript**

Replace `src/agent_office/web/app.js`:

```javascript
const TOKEN_KEY = "agentOfficeToken";
const defaultToken = localStorage.getItem(TOKEN_KEY) || "dev-token";
let state = { machines: [], sessions: [], agents: [], commands: [] };
let selectedSessionId = null;

const actions = [
  { action: "append_prompt", label: "Append prompt" },
  { action: "request_report", label: "Request report" },
  { action: "continue", label: "Continue" },
];

function headers() {
  return { Authorization: `Bearer ${defaultToken}`, "Content-Type": "application/json" };
}

async function fetchState() {
  const response = await fetch("/api/state", { headers: headers() });
  if (!response.ok) throw new Error(`state fetch failed: ${response.status}`);
  state = await response.json();
  render();
}

function machineFor(session) {
  return state.machines.find((machine) => machine.machine_id === session.machine_id);
}

function renderMachines() {
  const root = document.getElementById("machine-list");
  root.innerHTML = "";
  for (const machine of state.machines) {
    const item = document.createElement("button");
    item.className = `machine-item ${machine.health}`;
    item.type = "button";
    item.textContent = `${machine.hostname} · ${machine.health}`;
    root.appendChild(item);
  }
}

function renderSessions() {
  const root = document.getElementById("session-table");
  root.innerHTML = "";
  for (const session of state.sessions) {
    const row = document.createElement("tr");
    row.className = selectedSessionId === session.session_id ? "selected" : "";
    row.addEventListener("click", () => {
      selectedSessionId = session.session_id;
      render();
    });
    const machine = machineFor(session);
    row.innerHTML = `
      <td>${session.runtime_type}</td>
      <td>${session.project_name || "-"}</td>
      <td><span class="status ${session.status}">${session.status}</span></td>
      <td>${machine ? machine.hostname : session.machine_id}</td>
      <td>${session.progress_summary || session.current_task || "-"}</td>
    `;
    root.appendChild(row);
  }
}

function renderActions(session) {
  const container = document.createElement("div");
  container.className = "actions";
  for (const { action, label } of actions) {
    if (!session.capabilities.includes(action)) continue;
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.addEventListener("click", () => submitCommand(session, action));
    container.appendChild(button);
  }
  return container;
}

async function submitCommand(session, action) {
  const prompt = action === "append_prompt"
    ? window.prompt("Prompt to append")
    : action === "request_report"
      ? "Please summarize progress, blockers, and next step."
      : "Please continue the current task.";
  if (!prompt) return;
  await fetch("/api/commands", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({
      target_machine_id: session.machine_id,
      target_session_id: session.session_id,
      action,
      payload: { prompt },
      actor: "web-ui",
      audit_metadata: { source: "console" },
    }),
  });
  await fetchState();
}

function renderDetail() {
  const root = document.getElementById("session-detail");
  const session = state.sessions.find((item) => item.session_id === selectedSessionId) || state.sessions[0];
  if (!session) {
    root.innerHTML = "<h3>Select a session</h3><p class=\"muted\">Details and actions appear here.</p>";
    return;
  }
  selectedSessionId = session.session_id;
  root.innerHTML = `
    <h3>${session.project_name || session.session_id}</h3>
    <dl>
      <dt>Runtime</dt><dd>${session.runtime_type}</dd>
      <dt>Status</dt><dd>${session.status}</dd>
      <dt>Task</dt><dd>${session.current_task || "-"}</dd>
      <dt>Progress</dt><dd>${session.progress_summary || "-"}</dd>
    </dl>
  `;
  root.appendChild(renderActions(session));
}

function renderOffice() {
  const root = document.getElementById("office-view");
  root.innerHTML = "";
  for (const session of state.sessions) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = `desk ${session.status}`;
    card.textContent = `${session.runtime_type}: ${session.project_name || session.session_id}`;
    card.addEventListener("click", () => {
      selectedSessionId = session.session_id;
      render();
    });
    root.appendChild(card);
  }
}

function render() {
  renderMachines();
  renderSessions();
  renderDetail();
  renderOffice();
}

function connectWebSocket() {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.type === "state") {
      state = message.state;
      render();
    }
  };
  ws.onclose = () => setTimeout(connectWebSocket, 1500);
}

document.getElementById("refresh-button").addEventListener("click", fetchState);
fetchState().catch((error) => console.error(error));
connectWebSocket();
```

- [ ] **Step 5: Replace frontend CSS**

Replace `src/agent_office/web/styles.css`:

```css
:root {
  color-scheme: light;
  --bg: #f4f6f8;
  --panel: #ffffff;
  --border: #d8dee8;
  --text: #172033;
  --muted: #687386;
  --accent: #1f6feb;
  --good: #1a7f37;
  --warn: #9a6700;
  --bad: #cf222e;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: var(--bg);
  color: var(--text);
}

button {
  font: inherit;
  cursor: pointer;
}

.app-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
}

.sidebar {
  border-right: 1px solid var(--border);
  background: var(--panel);
  padding: 18px;
}

.main-panel {
  padding: 20px;
  min-width: 0;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.muted { color: var(--muted); }

.machine-list {
  display: grid;
  gap: 8px;
}

.machine-item {
  border: 1px solid var(--border);
  background: #f9fafb;
  border-radius: 8px;
  padding: 10px;
  text-align: left;
}

.machine-item.online { border-left: 4px solid var(--good); }
.machine-item.lost { border-left: 4px solid var(--bad); }

.console-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 16px;
  align-items: start;
}

.table-panel,
.detail-panel {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}

.detail-panel {
  padding: 16px;
}

.session-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.session-table th,
.session-table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: top;
}

.session-table tr.selected {
  background: #eef5ff;
}

.status {
  display: inline-flex;
  border-radius: 999px;
  padding: 2px 8px;
  background: #eef2f7;
}

.status.working { color: var(--accent); }
.status.waiting_input,
.status.waiting_permission,
.status.blocked { color: var(--warn); }
.status.lost { color: var(--bad); }
.status.completed { color: var(--good); }

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.actions button,
#refresh-button {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #f9fafb;
  padding: 8px 10px;
}

.office-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: 10px;
}

.desk {
  min-height: 72px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel);
  padding: 10px;
  text-align: left;
}

.desk.working { border-left: 4px solid var(--accent); }
.desk.lost { border-left: 4px solid var(--bad); }
.desk.completed { border-left: 4px solid var(--good); }

@media (max-width: 920px) {
  .app-shell,
  .console-grid {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 6: Run web asset tests to verify GREEN**

Run:

```bash
python -m pytest tests/test_web_assets.py -q
```

Expected: PASS, `3 passed`.

- [ ] **Step 7: Run full test suite**

Run:

```bash
python -m pytest -q
```

Expected: PASS, all current tests pass.

- [ ] **Step 8: Commit web console**

```bash
git add src/agent_office/web/index.html src/agent_office/web/app.js src/agent_office/web/styles.css tests/test_web_assets.py
git commit -m "feat: add Agent Office console UI"
```

---

### Task 8: Local Run Documentation And Smoke Verification

**Files:**
- Modify: `README.md`
- Test: `tests/test_readme_commands.py`

- [ ] **Step 1: Write failing README coverage test**

Create `tests/test_readme_commands.py`:

```python
from pathlib import Path


def test_readme_documents_server_collector_and_token() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "AGENT_OFFICE_TOKEN=dev-token agent-office-server --host 0.0.0.0 --port 8080" in readme
    assert "AGENT_OFFICE_TOKEN=dev-token agent-office-collector --central-url http://127.0.0.1:8080" in readme
    assert "append_prompt" in readme
    assert "request_report" in readme
    assert "continue" in readme
```

- [ ] **Step 2: Run README test to verify RED**

Run:

```bash
python -m pytest tests/test_readme_commands.py -q
```

Expected: FAIL because README does not document collector command and safe actions yet.

- [ ] **Step 3: Update README**

Replace `README.md`:

```markdown
# Agent Office

Agent Office is an internal operations console for Codex CLI, Claude Code, and Hermes/self-hosted agents.

The MVP uses a central service plus lightweight machine collectors:

```text
runtime hooks/logs/probes -> collector -> central event store -> projector -> web UI
web UI -> command queue -> collector -> runtime adapter -> command result
```

## MVP capabilities

- central event ingestion and projected state
- machine collector with runtime adapters
- safe control commands: `append_prompt`, `request_report`, `continue`
- dense console UI and simple Office/Building projection
- shared token auth for trusted internal use

## Install for local development

```bash
python -m pip install -e '.[dev]'
```

## Run tests

```bash
python -m pytest
```

## Run central locally on port 8080

```bash
AGENT_OFFICE_TOKEN=dev-token agent-office-server --host 0.0.0.0 --port 8080
```

Open:

```text
http://localhost:8080
```

## Run the collector against local central

```bash
AGENT_OFFICE_TOKEN=dev-token agent-office-collector --central-url http://127.0.0.1:8080
```

The first collector implementation includes a fake adapter for end-to-end smoke testing. Codex, Claude Code, and Hermes adapters normalize runtime-specific signals into the same event schema.

## Security model

The MVP is for trusted internal use. Every API request uses the shared `AGENT_OFFICE_TOKEN`. Every control action is persisted as a command record with actor, target, payload summary, status, timestamps, and result.

High-risk controls such as kill, restart, and pause are outside the MVP.
```

- [ ] **Step 4: Run README test to verify GREEN**

Run:

```bash
python -m pytest tests/test_readme_commands.py -q
```

Expected: PASS, `1 passed`.

- [ ] **Step 5: Run all tests**

Run:

```bash
python -m pytest -q
```

Expected: PASS, all tests pass.

- [ ] **Step 6: Run an import smoke check**

Run:

```bash
python -c "from agent_office.server import create_app; app = create_app('agent-office-smoke.sqlite', 'dev-token'); print(app.title)"
```

Expected output contains:

```text
Agent Office
```

- [ ] **Step 7: Commit docs and smoke coverage**

```bash
git add README.md tests/test_readme_commands.py
git commit -m "docs: document Agent Office local run flow"
```

---

## Plan Self-Review

Spec coverage:

- Central API and storage are covered by Tasks 2, 3, and 4.
- Collector and fake adapter are covered by Task 5.
- Codex, Claude Code, and Hermes adapter normalizers are covered by Task 6.
- Console UI and Office projection are covered by Task 7.
- Shared token auth and command audit are covered by Tasks 2 and 4.
- Local run documentation is covered by Task 8.

No implementation task depends on Office animation state. The Office view consumes the same projected state as the console.

Known implementation constraints:

- The first `append_prompt` transport is schema/capability-level only until a reliable runtime-specific transport is implemented for each adapter.
- Hermes control depth depends on the available Hermes API; the MVP mapper only exposes `append_prompt` when the snapshot explicitly says `can_accept_prompt`.
- SQLite is the starting backend; table shape is kept simple enough to migrate to Postgres later.
