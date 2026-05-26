from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_office.models import ControlCommand, RuntimeType


def parse_timestamp(value: object, fallback: datetime) -> datetime:
    if not isinstance(value, str) or not value:
        return fallback
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return fallback
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def read_jsonl_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if isinstance(value, dict):
            records.append(value)
    return records


def record_payload(record: dict[str, Any]) -> dict[str, Any]:
    payload = record.get("payload")
    if isinstance(payload, dict):
        return payload
    return {
        key: value
        for key, value in record.items()
        if key not in {"event", "event_name", "hook_event_name", "timestamp", "type"}
    }


def append_command_outbox(path: Path, runtime_type: RuntimeType, command: ControlCommand) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = command.model_dump(mode="json")
    record["runtime_type"] = runtime_type.value
    record["written_at"] = datetime.now(UTC).isoformat()
    with path.open("a", encoding="utf-8") as handle:
        json.dump(record, handle, sort_keys=True)
        handle.write("\n")
