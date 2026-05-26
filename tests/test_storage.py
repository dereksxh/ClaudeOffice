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
