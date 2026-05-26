from datetime import UTC, datetime

from fastapi.testclient import TestClient

from agent_office.collector.adapters.fake import FakeAdapter
from agent_office.collector.client import CollectorClient
from agent_office.collector.runner import collect_once
from agent_office.models import CommandAction, EventType, RuntimeType
from agent_office.server import create_app


def test_fake_adapter_emits_heartbeat_and_session_event() -> None:
    adapter = FakeAdapter(machine_id="machine-a", hostname="worker-a")

    events = adapter.snapshot_events(now=datetime(2026, 5, 26, 3, 0, tzinfo=UTC))

    assert events[0].event_type == EventType.MACHINE_HEARTBEAT
    assert events[0].machine_id == "machine-a"
    assert events[1].runtime_type == RuntimeType.HERMES
    assert events[1].session_id == "fake-session"


def test_collector_posts_events_to_central(tmp_path) -> None:
    app = create_app(db_path=tmp_path / "agent-office.sqlite", api_token="test-token")
    test_client = TestClient(app)
    collector_client = CollectorClient.for_test_client(test_client, token="test-token")
    adapter = FakeAdapter(machine_id="machine-a", hostname="worker-a")

    collect_once(
        client=collector_client,
        adapters=[adapter],
        now=datetime(2026, 5, 26, 3, 0, tzinfo=UTC),
    )

    state = test_client.get(
        "/api/state",
        headers={"Authorization": "Bearer test-token"},
    ).json()
    assert state["machines"][0]["machine_id"] == "machine-a"
    assert state["sessions"][0]["session_id"] == "fake-session"


def test_collector_leases_and_applies_supported_command(tmp_path) -> None:
    app = create_app(db_path=tmp_path / "agent-office.sqlite", api_token="test-token")
    test_client = TestClient(app)
    collector_client = CollectorClient.for_test_client(test_client, token="test-token")
    adapter = FakeAdapter(machine_id="machine-a", hostname="worker-a")

    create_response = test_client.post(
        "/api/commands",
        headers={"Authorization": "Bearer test-token"},
        json={
            "target_machine_id": "machine-a",
            "target_session_id": "fake-session",
            "action": CommandAction.REQUEST_REPORT,
            "payload": {"prompt": "Report progress."},
            "actor": "derek",
        },
    )
    assert create_response.status_code == 201

    collect_once(
        client=collector_client,
        adapters=[adapter],
        now=datetime(2026, 5, 26, 3, 1, tzinfo=UTC),
    )

    state = test_client.get(
        "/api/state",
        headers={"Authorization": "Bearer test-token"},
    ).json()
    assert state["commands"][0]["status"] == "applied"
    assert adapter.applied_commands == ["request_report"]
