from __future__ import annotations

import argparse
import os
import time
from datetime import UTC, datetime

from agent_office.collector.adapters.base import RuntimeAdapter
from agent_office.collector.adapters.fake import FakeAdapter
from agent_office.collector.client import CollectorClient
from agent_office.models import CommandStatus


def collect_once(client: CollectorClient, adapters: list[RuntimeAdapter], now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    for adapter in adapters:
        for event in adapter.snapshot_events(now):
            client.post_event(event)

        commands = client.lease_commands(adapter.machine_id)
        for command in commands:
            result = adapter.apply_command(command)
            client.post_command_result(
                command.command_id,
                CommandStatus.APPLIED if result.applied else CommandStatus.FAILED,
                result.summary,
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--central-url", default=os.environ.get("AGENT_OFFICE_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--machine-id", default=os.uname().nodename)
    parser.add_argument("--hostname", default=os.uname().nodename)
    parser.add_argument("--interval", type=float, default=3.0)
    args = parser.parse_args()

    token = os.environ.get("AGENT_OFFICE_TOKEN", "dev-token")
    client = CollectorClient(base_url=args.central_url, token=token)
    adapters: list[RuntimeAdapter] = [FakeAdapter(machine_id=args.machine_id, hostname=args.hostname)]

    while True:
        collect_once(client, adapters)
        time.sleep(args.interval)
