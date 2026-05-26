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
    TokenUsageModelBreakdown,
    TokenUsagePeriod,
    TokenUsageSnapshot,
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


def test_token_usage_snapshot_tracks_runtime_totals() -> None:
    usage = TokenUsageSnapshot(
        machine_id="machine-a",
        runtime_type=RuntimeType.CODEX,
        scope="local_logs",
        label="Codex local usage",
        total_tokens=1234,
        input_tokens=900,
        cached_input_tokens=200,
        output_tokens=100,
        reasoning_output_tokens=34,
        billable_unit="credits",
        billable_amount=1.25,
        budget_amount=5000,
        budget_used_ratio=0.00025,
        request_count=5,
        session_count=2,
        updated_at=datetime(2026, 5, 26, 3, 0, tzinfo=UTC),
        source_ref="codex:sessions",
        periods=[
            TokenUsagePeriod(
                period="today",
                start_at=datetime(2026, 5, 26, 0, 0, tzinfo=UTC),
                end_at=datetime(2026, 5, 26, 3, 0, tzinfo=UTC),
                total_tokens=100,
                billable_unit="credits",
                billable_amount=0.1,
            )
        ],
        model_breakdown=[
            TokenUsageModelBreakdown(
                model="gpt-5.4",
                total_tokens=1234,
                input_tokens=900,
                cached_input_tokens=200,
                output_tokens=100,
                billable_unit="credits",
                billable_amount=1.25,
            )
        ],
    )

    assert usage.total_tokens == 1234
    assert usage.runtime_type == RuntimeType.CODEX
    assert usage.periods[0].period == "today"
    assert usage.model_breakdown[0].model == "gpt-5.4"


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
