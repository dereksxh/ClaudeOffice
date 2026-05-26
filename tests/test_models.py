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
