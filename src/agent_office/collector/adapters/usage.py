from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from agent_office.collector.adapters.base import AdapterCommandResult
from agent_office.collector.adapters.files import parse_timestamp
from agent_office.collector.usage_accounting import UsageBucket, period_payload, usage_period_bounds
from agent_office.models import ControlCommand, EventRecord, EventType, RuntimeType


def _int_value(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


class ClaudeCodeUsageAdapter:
    runtime_type = RuntimeType.CLAUDE_CODE

    def __init__(
        self,
        machine_id: str,
        projects_dir: str | Path,
        usage_timezone: str = "Asia/Singapore",
        week_start_day: int = 0,
        week_start_hour: int = 0,
    ) -> None:
        self.machine_id = machine_id
        self.projects_dir = Path(projects_dir)
        self.usage_timezone = usage_timezone
        self.week_start_day = week_start_day
        self.week_start_hour = week_start_hour

    def snapshot_events(self, now: datetime) -> list[EventRecord]:
        if not self.projects_dir.exists():
            return []

        bounds = usage_period_bounds(now, self.usage_timezone, self.week_start_day, self.week_start_hour)
        all_usage = UsageBucket()
        today_usage = UsageBucket()
        week_usage = UsageBucket()
        seen_usage_keys: set[str] = set()
        latest_timestamp = now

        files = sorted(self.projects_dir.glob("**/*.jsonl"))
        for path in files:
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
                record_timestamp = parse_timestamp(record.get("timestamp"), latest_timestamp)
                latest_timestamp = record_timestamp
                message = record.get("message") if isinstance(record.get("message"), dict) else {}
                usage = message.get("usage") if isinstance(message.get("usage"), dict) else None
                if usage is None:
                    continue

                usage_key = self._usage_key(path, line_number, record, message)
                if usage_key in seen_usage_keys:
                    continue
                seen_usage_keys.add(usage_key)
                model = message.get("model") if isinstance(message.get("model"), str) else "unknown"
                tokens = self._usage_tokens(usage)
                all_usage.add(model, tokens, str(path))
                if record_timestamp >= bounds["today"]:
                    today_usage.add(model, tokens, str(path))
                if record_timestamp >= bounds["week"]:
                    week_usage.add(model, tokens, str(path))

        payload = all_usage.to_payload(RuntimeType.CLAUDE_CODE, "usd")
        periods = [
            period_payload("today", today_usage, RuntimeType.CLAUDE_CODE, "usd", bounds["today"], now),
            period_payload("week", week_usage, RuntimeType.CLAUDE_CODE, "usd", bounds["week"], now),
        ]

        raw = (
            f"{self.machine_id}:{self.projects_dir}:{len(files)}:{len(seen_usage_keys)}:"
            f"{payload['total_tokens']}:{payload['billable_amount']}:{now.isoformat()}"
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
                    **payload,
                    "periods": periods,
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

    def _usage_tokens(self, usage: dict[str, Any]) -> dict[str, int]:
        input_tokens = _int_value(usage.get("input_tokens"))
        cache_creation = _int_value(usage.get("cache_creation_input_tokens"))
        cache_read = _int_value(usage.get("cache_read_input_tokens"))
        output_tokens = _int_value(usage.get("output_tokens"))
        cache_creation_detail = usage.get("cache_creation") if isinstance(usage.get("cache_creation"), dict) else {}
        cache_creation_5m = _int_value(cache_creation_detail.get("ephemeral_5m_input_tokens"))
        cache_creation_1h = _int_value(cache_creation_detail.get("ephemeral_1h_input_tokens"))
        return {
            "input_tokens": input_tokens,
            "cache_creation_input_tokens": cache_creation,
            "cache_creation_5m_input_tokens": cache_creation_5m,
            "cache_creation_1h_input_tokens": cache_creation_1h,
            "cache_read_input_tokens": cache_read,
            "cached_input_tokens": cache_creation + cache_read,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + cache_creation + cache_read + output_tokens,
        }
