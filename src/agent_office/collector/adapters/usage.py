from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from agent_office.collector.adapters.base import AdapterCommandResult
from agent_office.collector.adapters.files import parse_timestamp
from agent_office.models import ControlCommand, EventRecord, EventType, RuntimeType


def _int_value(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


class ClaudeCodeUsageAdapter:
    runtime_type = RuntimeType.CLAUDE_CODE

    def __init__(self, machine_id: str, projects_dir: str | Path) -> None:
        self.machine_id = machine_id
        self.projects_dir = Path(projects_dir)

    def snapshot_events(self, now: datetime) -> list[EventRecord]:
        if not self.projects_dir.exists():
            return []

        totals = {
            "input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }
        seen_usage_keys: set[str] = set()
        session_count = 0
        latest_timestamp = now

        files = sorted(self.projects_dir.glob("**/*.jsonl"))
        for path in files:
            file_has_usage = False
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue

            for line_number, line in enumerate(lines, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue
                latest_timestamp = parse_timestamp(record.get("timestamp"), latest_timestamp)
                message = record.get("message") if isinstance(record.get("message"), dict) else {}
                usage = message.get("usage") if isinstance(message.get("usage"), dict) else None
                if usage is None:
                    continue

                usage_key = self._usage_key(path, line_number, record, message)
                if usage_key in seen_usage_keys:
                    continue
                seen_usage_keys.add(usage_key)
                file_has_usage = True

                input_tokens = _int_value(usage.get("input_tokens"))
                cache_creation = _int_value(usage.get("cache_creation_input_tokens"))
                cache_read = _int_value(usage.get("cache_read_input_tokens"))
                output_tokens = _int_value(usage.get("output_tokens"))
                totals["input_tokens"] += input_tokens
                totals["cache_creation_input_tokens"] += cache_creation
                totals["cache_read_input_tokens"] += cache_read
                totals["cached_input_tokens"] += cache_creation + cache_read
                totals["output_tokens"] += output_tokens
                totals["total_tokens"] += input_tokens + cache_creation + cache_read + output_tokens

            if file_has_usage:
                session_count += 1

        raw = (
            f"{self.machine_id}:{self.projects_dir}:{len(files)}:{len(seen_usage_keys)}:"
            f"{totals['total_tokens']}:{now.isoformat()}"
        )
        return [
            EventRecord(
                event_id="claude-usage-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24],
                machine_id=self.machine_id,
                runtime_type=RuntimeType.CLAUDE_CODE,
                event_type=EventType.USAGE_SNAPSHOT,
                timestamp=now,
                payload={
                    "scope": "local_logs",
                    "label": "Claude Code local usage",
                    **totals,
                    "request_count": len(seen_usage_keys),
                    "session_count": session_count,
                    "latest_usage_at": latest_timestamp.isoformat(),
                },
                source_ref=str(self.projects_dir),
            )
        ]

    def apply_command(self, command: ControlCommand) -> AdapterCommandResult:
        return AdapterCommandResult(False, "claude code usage adapter is read-only")

    def _usage_key(self, path: Path, line_number: int, record: dict[str, Any], message: dict[str, Any]) -> str:
        message_id = message.get("id")
        if isinstance(message_id, str) and message_id:
            return f"message:{message_id}"
        request_id = record.get("requestId")
        if isinstance(request_id, str) and request_id:
            return f"request:{request_id}"
        return f"line:{path}:{line_number}"
