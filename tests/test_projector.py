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


def test_session_updated_refreshes_metadata_and_capabilities() -> None:
    events = [
        EventRecord(
            event_id="evt-session-started",
            machine_id="machine-a",
            runtime_type=RuntimeType.CODEX,
            session_id="codex-1",
            event_type=EventType.SESSION_STARTED,
            timestamp=datetime(2026, 5, 26, 3, 0, tzinfo=UTC),
            payload={
                "cwd": "/old",
                "project_name": "old-project",
                "model": "gpt-4.1",
                "current_task": "Old task",
                "progress_summary": "Old progress",
                "capabilities": ["append_prompt"],
            },
            source_ref="hook:start",
        ),
        EventRecord(
            event_id="evt-session-updated",
            machine_id="machine-a",
            runtime_type=RuntimeType.CODEX,
            session_id="codex-1",
            event_type=EventType.SESSION_UPDATED,
            timestamp=datetime(2026, 5, 26, 3, 1, tzinfo=UTC),
            payload={
                "cwd": "/new",
                "project_name": "new-project",
                "model": "gpt-5",
                "current_task": "New task",
                "progress_summary": "New progress",
                "capabilities": ["request_report", "continue"],
            },
            source_ref="hook:update",
        ),
    ]

    state = project_state(events, [], now=datetime(2026, 5, 26, 3, 2, tzinfo=UTC))

    session = state.sessions[0]
    assert session.cwd == "/new"
    assert session.project_name == "new-project"
    assert session.model == "gpt-5"
    assert session.current_task == "New task"
    assert session.progress_summary == "New progress"
    assert session.capabilities == [Capability.REQUEST_REPORT, Capability.CONTINUE]
    assert session.source_ref == "hook:update"


def test_projector_updates_task_from_user_prompt_event() -> None:
    events = [
        EventRecord(
            event_id="evt-session-started",
            machine_id="machine-a",
            runtime_type=RuntimeType.CODEX,
            session_id="codex-1",
            event_type=EventType.SESSION_STARTED,
            timestamp=datetime(2026, 5, 26, 3, 0, tzinfo=UTC),
            payload={
                "current_task": "Old task",
                "progress_summary": "Old progress",
            },
        ),
        EventRecord(
            event_id="evt-user-prompt",
            machine_id="machine-a",
            runtime_type=RuntimeType.CODEX,
            session_id="codex-1",
            event_type=EventType.USER_PROMPT,
            timestamp=datetime(2026, 5, 26, 3, 1, tzinfo=UTC),
            payload={
                "current_task": "Build Agent Office",
                "progress_summary": "User prompt submitted",
            },
        ),
    ]

    state = project_state(events, [], now=datetime(2026, 5, 26, 3, 2, tzinfo=UTC))

    assert state.sessions[0].current_task == "Build Agent Office"
    assert state.sessions[0].progress_summary == "User prompt submitted"


def test_projector_marks_tool_finished_progress() -> None:
    events = [
        EventRecord(
            event_id="evt-session-started",
            machine_id="machine-a",
            runtime_type=RuntimeType.CODEX,
            session_id="codex-1",
            event_type=EventType.SESSION_STARTED,
            timestamp=datetime(2026, 5, 26, 3, 0, tzinfo=UTC),
            payload={"project_name": "repo"},
        ),
        EventRecord(
            event_id="evt-tool-started",
            machine_id="machine-a",
            runtime_type=RuntimeType.CODEX,
            session_id="codex-1",
            agent_id="main",
            event_type=EventType.TOOL_STARTED,
            timestamp=datetime(2026, 5, 26, 3, 1, tzinfo=UTC),
            payload={"tool_name": "Bash"},
        ),
        EventRecord(
            event_id="evt-tool-finished",
            machine_id="machine-a",
            runtime_type=RuntimeType.CODEX,
            session_id="codex-1",
            agent_id="main",
            event_type=EventType.TOOL_FINISHED,
            timestamp=datetime(2026, 5, 26, 3, 2, tzinfo=UTC),
            payload={"tool_name": "Bash"},
        ),
    ]

    state = project_state(events, [], now=datetime(2026, 5, 26, 3, 3, tzinfo=UTC))

    assert state.sessions[0].status == SessionStatus.WORKING
    assert state.sessions[0].progress_summary == "Finished tool: Bash"


def test_agent_stopped_does_not_complete_parent_session() -> None:
    events = [
        EventRecord(
            event_id="evt-session-started",
            machine_id="machine-a",
            runtime_type=RuntimeType.CODEX,
            session_id="codex-1",
            event_type=EventType.SESSION_STARTED,
            timestamp=datetime(2026, 5, 26, 3, 0, tzinfo=UTC),
            payload={"project_name": "repo"},
        ),
        EventRecord(
            event_id="evt-agent-updated",
            machine_id="machine-a",
            runtime_type=RuntimeType.CODEX,
            session_id="codex-1",
            agent_id="agent-1",
            event_type=EventType.AGENT_UPDATED,
            timestamp=datetime(2026, 5, 26, 3, 1, tzinfo=UTC),
            payload={"task_description": "Inspect tests"},
        ),
        EventRecord(
            event_id="evt-agent-stopped",
            machine_id="machine-a",
            runtime_type=RuntimeType.CODEX,
            session_id="codex-1",
            agent_id="agent-1",
            event_type=EventType.AGENT_STOPPED,
            timestamp=datetime(2026, 5, 26, 3, 2, tzinfo=UTC),
            payload={"progress_summary": "Done inspecting tests"},
        ),
    ]

    state = project_state(events, [], now=datetime(2026, 5, 26, 3, 3, tzinfo=UTC))

    assert state.sessions[0].status == SessionStatus.WORKING
    assert state.agents[0].status == SessionStatus.COMPLETED
    assert state.agents[0].progress_summary == "Done inspecting tests"


def test_projector_sorts_commands_by_created_at_and_id() -> None:
    later = ControlCommand(
        command_id="cmd-1",
        target_machine_id="machine-a",
        target_session_id="codex-1",
        action=CommandAction.CONTINUE,
        actor="derek",
        created_at=datetime(2026, 5, 26, 3, 1, tzinfo=UTC),
    )
    same_time_second = ControlCommand(
        command_id="cmd-b",
        target_machine_id="machine-a",
        target_session_id="codex-1",
        action=CommandAction.REQUEST_REPORT,
        actor="derek",
        created_at=datetime(2026, 5, 26, 3, 0, tzinfo=UTC),
    )
    same_time_first = ControlCommand(
        command_id="cmd-a",
        target_machine_id="machine-a",
        target_session_id="codex-1",
        action=CommandAction.APPEND_PROMPT,
        actor="derek",
        created_at=datetime(2026, 5, 26, 3, 0, tzinfo=UTC),
    )

    state = project_state(
        [],
        [later, same_time_second, same_time_first],
        now=datetime(2026, 5, 26, 3, 2, tzinfo=UTC),
    )

    assert [command.command_id for command in state.commands] == ["cmd-a", "cmd-b", "cmd-1"]
