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
    value = value.astimezone(UTC)
    return value.isoformat()


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def init_db(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
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
    if limit <= 0:
        raise ValueError("limit must be greater than 0")

    cutoff = now - lease_ttl
    try:
        conn.execute("BEGIN IMMEDIATE")
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

        refreshed = [
            conn.execute("SELECT * FROM commands WHERE command_id = ?", (command_id,)).fetchone()
            for command_id in command_ids
        ]
        conn.commit()
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise

    return [_row_to_command(row) for row in refreshed if row is not None]


def complete_command(
    conn: sqlite3.Connection,
    command_id: str,
    status: CommandStatus,
    result_summary: str,
    completed_at: datetime,
) -> bool:
    cursor = conn.execute(
        """
        UPDATE commands
        SET status = ?, result_summary = ?, completed_at = ?
        WHERE command_id = ?
        """,
        (status.value, result_summary, _dt(completed_at), command_id),
    )
    conn.commit()
    return cursor.rowcount == 1
