from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from agent_office.collector.adapters.base import AdapterCommandResult, RuntimeAdapter
from agent_office.collector.adapters.claude_code import ClaudeHookLogAdapter
from agent_office.collector.adapters.codex import CodexHookLogAdapter, CodexSessionDirectoryAdapter
from agent_office.collector.adapters.fake import FakeAdapter
from agent_office.collector.adapters.hermes import HermesGatewayStateAdapter, HermesSnapshotFileAdapter
from agent_office.collector.adapters.usage import ClaudeCodeUsageAdapter
from agent_office.collector.client import CollectorClient
from agent_office.models import CommandStatus, ControlCommand, EventRecord, EventType


def _truthy(value: str | None) -> bool:
    return value is not None and value.lower() in {"1", "true", "yes", "on"}


def _command_outbox_path(command_outbox_dir: str | None, runtime_name: str) -> Path | None:
    if not command_outbox_dir:
        return None
    return Path(command_outbox_dir) / f"{runtime_name}-commands.jsonl"


def build_adapters(args: argparse.Namespace) -> list[RuntimeAdapter]:
    adapters: list[RuntimeAdapter] = []

    if args.codex_hook_log:
        adapters.append(
            CodexHookLogAdapter(
                machine_id=args.machine_id,
                hook_log_path=args.codex_hook_log,
                command_outbox_path=_command_outbox_path(args.command_outbox_dir, "codex"),
            )
        )
    if args.codex_sessions_dir:
        adapters.append(
            CodexSessionDirectoryAdapter(
                machine_id=args.machine_id,
                sessions_dir=args.codex_sessions_dir,
                usage_timezone=getattr(args, "usage_timezone", "Asia/Singapore"),
                week_start_day=getattr(args, "usage_week_start_day", 0),
                week_start_hour=getattr(args, "usage_week_start_hour", 0),
                weekly_credit_budget=getattr(args, "codex_weekly_credit_budget", 5000.0),
            )
        )
    if args.claude_hook_log:
        adapters.append(
            ClaudeHookLogAdapter(
                machine_id=args.machine_id,
                hook_log_path=args.claude_hook_log,
                command_outbox_path=_command_outbox_path(args.command_outbox_dir, "claude-code"),
            )
        )
    if args.claude_projects_dir:
        adapters.append(
            ClaudeCodeUsageAdapter(
                machine_id=args.machine_id,
                projects_dir=args.claude_projects_dir,
                usage_timezone=getattr(args, "usage_timezone", "Asia/Singapore"),
                week_start_day=getattr(args, "usage_week_start_day", 0),
                week_start_hour=getattr(args, "usage_week_start_hour", 0),
            )
        )
    if args.hermes_snapshot:
        adapters.append(
            HermesSnapshotFileAdapter(
                machine_id=args.machine_id,
                snapshot_path=args.hermes_snapshot,
                command_outbox_path=_command_outbox_path(args.command_outbox_dir, "hermes"),
            )
        )
    if args.hermes_home:
        adapters.append(
            HermesGatewayStateAdapter(
                machine_id=args.machine_id,
                hermes_home=args.hermes_home,
            )
        )
    if args.enable_fake:
        adapters.append(FakeAdapter(machine_id=args.machine_id, hostname=args.hostname))

    return adapters


def _apply_command(command: ControlCommand, adapters: list[RuntimeAdapter]) -> AdapterCommandResult:
    candidates = [adapter for adapter in adapters if adapter.machine_id == command.target_machine_id]
    target_runtime_type = command.audit_metadata.get("target_runtime_type")
    if isinstance(target_runtime_type, str):
        candidates = [adapter for adapter in candidates if adapter.runtime_type.value == target_runtime_type]
    if not candidates:
        return AdapterCommandResult(False, "no adapter configured for command target")
    return candidates[0].apply_command(command)


def _heartbeat_events(adapters: list[RuntimeAdapter], now: datetime) -> list[EventRecord]:
    by_machine: dict[str, list[RuntimeAdapter]] = {}
    for adapter in adapters:
        by_machine.setdefault(adapter.machine_id, []).append(adapter)

    events: list[EventRecord] = []
    for machine_id, machine_adapters in sorted(by_machine.items()):
        runtime_inventory = sorted({adapter.runtime_type.value for adapter in machine_adapters})
        hostname = str(getattr(machine_adapters[0], "hostname", machine_id))
        events.append(
            EventRecord(
                event_id=f"{machine_id}:collector-heartbeat:{int(now.timestamp())}",
                machine_id=machine_id,
                runtime_type=machine_adapters[0].runtime_type,
                event_type=EventType.MACHINE_HEARTBEAT,
                timestamp=now,
                payload={
                    "hostname": hostname,
                    "collector_version": "0.1.0",
                    "runtime_inventory": runtime_inventory,
                },
                source_ref="collector:heartbeat",
            )
        )
    return events


def collect_once(client: CollectorClient, adapters: list[RuntimeAdapter], now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    for event in _heartbeat_events(adapters, now):
        client.post_event(event)

    for adapter in adapters:
        for event in adapter.snapshot_events(now):
            client.post_event(event)

    for machine_id in sorted({adapter.machine_id for adapter in adapters}):
        commands = client.lease_commands(machine_id)
        for command in commands:
            result = _apply_command(command, adapters)
            client.post_command_result(
                command.command_id,
                machine_id,
                CommandStatus.APPLIED if result.applied else CommandStatus.FAILED,
                result.summary,
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--central-url", default=os.environ.get("AGENT_OFFICE_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--machine-id", default=os.uname().nodename)
    parser.add_argument("--hostname", default=os.uname().nodename)
    parser.add_argument("--interval", type=float, default=3.0)
    parser.add_argument("--codex-hook-log", default=os.environ.get("AGENT_OFFICE_CODEX_HOOK_LOG"))
    parser.add_argument("--codex-sessions-dir", default=os.environ.get("AGENT_OFFICE_CODEX_SESSIONS_DIR"))
    parser.add_argument("--claude-hook-log", default=os.environ.get("AGENT_OFFICE_CLAUDE_HOOK_LOG"))
    parser.add_argument("--claude-projects-dir", default=os.environ.get("AGENT_OFFICE_CLAUDE_PROJECTS_DIR"))
    parser.add_argument("--usage-timezone", default=os.environ.get("AGENT_OFFICE_USAGE_TIMEZONE", "Asia/Singapore"))
    parser.add_argument(
        "--usage-week-start-day",
        type=int,
        default=int(os.environ.get("AGENT_OFFICE_USAGE_WEEK_START_DAY", "0")),
    )
    parser.add_argument(
        "--usage-week-start-hour",
        type=int,
        default=int(os.environ.get("AGENT_OFFICE_USAGE_WEEK_START_HOUR", "0")),
    )
    parser.add_argument(
        "--codex-weekly-credit-budget",
        type=float,
        default=float(os.environ.get("AGENT_OFFICE_CODEX_WEEKLY_CREDIT_BUDGET", "5000")),
    )
    parser.add_argument("--hermes-snapshot", default=os.environ.get("AGENT_OFFICE_HERMES_SNAPSHOT"))
    parser.add_argument("--hermes-home", default=os.environ.get("AGENT_OFFICE_HERMES_HOME"))
    parser.add_argument("--command-outbox-dir", default=os.environ.get("AGENT_OFFICE_COMMAND_OUTBOX_DIR"))
    parser.add_argument("--enable-fake", action="store_true", default=_truthy(os.environ.get("AGENT_OFFICE_ENABLE_FAKE")))
    args = parser.parse_args()

    token = os.environ.get("AGENT_OFFICE_TOKEN")
    if not token:
        raise SystemExit("AGENT_OFFICE_TOKEN is required")
    client = CollectorClient(base_url=args.central_url, token=token)
    adapters = build_adapters(args)

    while True:
        try:
            collect_once(client, adapters)
        except Exception as exc:
            print(f"collector iteration failed: {exc}", file=sys.stderr)
        time.sleep(args.interval)
