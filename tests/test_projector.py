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
