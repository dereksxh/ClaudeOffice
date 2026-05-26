from __future__ import annotations

from datetime import datetime

from agent_office.collector.adapters.base import AdapterCommandResult
from agent_office.models import Capability, CommandAction, ControlCommand, EventRecord, EventType, RuntimeType


class FakeAdapter:
    runtime_type = RuntimeType.HERMES

    def __init__(self, machine_id: str, hostname: str) -> None:
        self.machine_id = machine_id
        self.hostname = hostname
        self.applied_commands: list[str] = []

    def snapshot_events(self, now: datetime) -> list[EventRecord]:
        return [
            EventRecord(
                event_id=f"{self.machine_id}:heartbeat:{int(now.timestamp())}",
                machine_id=self.machine_id,
                runtime_type=RuntimeType.HERMES,
                event_type=EventType.MACHINE_HEARTBEAT,
                timestamp=now,
                payload={
                    "hostname": self.hostname,
                    "collector_version": "0.1.0",
                    "runtime_inventory": [RuntimeType.HERMES.value],
                },
                source_ref="fake:heartbeat",
            ),
            EventRecord(
                event_id=f"{self.machine_id}:fake-session:{int(now.timestamp())}",
                machine_id=self.machine_id,
                runtime_type=RuntimeType.HERMES,
                session_id="fake-session",
                agent_id="main",
                event_type=EventType.SESSION_STARTED,
                timestamp=now,
                payload={
                    "project_name": "fake-project",
                    "current_task": "Fake collector smoke",
                    "capabilities": [Capability.REQUEST_REPORT.value, Capability.CONTINUE.value],
                },
                source_ref="fake:session",
            ),
        ]

    def apply_command(self, command: ControlCommand) -> AdapterCommandResult:
        if command.action not in {CommandAction.REQUEST_REPORT, CommandAction.CONTINUE}:
            return AdapterCommandResult(False, f"unsupported action: {command.action.value}")
        self.applied_commands.append(command.action.value)
        return AdapterCommandResult(True, f"{command.action.value} applied to {command.target_session_id}")
