from datetime import UTC, datetime

from fastapi.testclient import TestClient

from agent_office.models import CommandAction, EventType, RuntimeType
from agent_office.server import create_app


def test_ingest_event_and_get_projected_state(tmp_path) -> None:
    app = create_app(db_path=tmp_path / "agent-office.sqlite", api_token="test-token")
    client = TestClient(app)

    response = client.post(
        "/api/events",
        headers={"Authorization": "Bearer test-token"},
        json={
            "event_id": "evt-1",
            "machine_id": "machine-a",
            "runtime_type": RuntimeType.CODEX,
            "session_id": "codex-1",
            "event_type": EventType.SESSION_STARTED,
            "timestamp": datetime(2026, 5, 26, 3, 0, tzinfo=UTC).isoformat(),
            "payload": {
                "project_name": "repo",
                "capabilities": ["request_report", "continue"],
            },
        },
    )

    assert response.status_code == 202

    state = client.get(
        "/api/state",
        headers={"Authorization": "Bearer test-token"},
    ).json()

    assert state["sessions"][0]["session_id"] == "codex-1"
    assert state["sessions"][0]["project_name"] == "repo"


def test_rejects_missing_token(tmp_path) -> None:
    app = create_app(db_path=tmp_path / "agent-office.sqlite", api_token="test-token")
    client = TestClient(app)

    response = client.get("/api/state")

    assert response.status_code == 401


def test_websocket_initial_state_message_is_wrapped(tmp_path) -> None:
    app = create_app(db_path=tmp_path / "agent-office.sqlite", api_token="test-token")
    client = TestClient(app)

    with client.websocket_connect("/ws") as websocket:
        message = websocket.receive_json()

    assert message["type"] == "state"
    assert "state" in message
    assert message["state"]["sessions"] == []


def test_websocket_broadcast_state_message_is_wrapped(tmp_path) -> None:
    app = create_app(db_path=tmp_path / "agent-office.sqlite", api_token="test-token")
    client = TestClient(app)

    with client.websocket_connect("/ws") as websocket:
        websocket.receive_json()

        response = client.post(
            "/api/events",
            headers={"Authorization": "Bearer test-token"},
            json={
                "event_id": "evt-1",
                "machine_id": "machine-a",
                "runtime_type": RuntimeType.CODEX,
                "session_id": "codex-1",
                "event_type": EventType.SESSION_STARTED,
                "timestamp": datetime(2026, 5, 26, 3, 0, tzinfo=UTC).isoformat(),
                "payload": {
                    "project_name": "repo",
                    "capabilities": ["request_report", "continue"],
                },
            },
        )
        message = websocket.receive_json()

    assert response.status_code == 202
    assert message["type"] == "state"
    assert "state" in message
    assert message["state"]["sessions"][0]["session_id"] == "codex-1"


def test_create_lease_and_complete_command(tmp_path) -> None:
    app = create_app(db_path=tmp_path / "agent-office.sqlite", api_token="test-token")
    client = TestClient(app)
    headers = {"Authorization": "Bearer test-token"}

    create_response = client.post(
        "/api/commands",
        headers=headers,
        json={
            "target_machine_id": "machine-a",
            "target_session_id": "codex-1",
            "action": CommandAction.REQUEST_REPORT,
            "payload": {"prompt": "Report progress."},
            "actor": "derek",
            "audit_metadata": {"source": "test"},
        },
    )

    assert create_response.status_code == 201
    command_id = create_response.json()["command_id"]

    lease_response = client.post(
        "/api/collector/commands/lease",
        headers=headers,
        json={"machine_id": "machine-a", "limit": 5},
    )
    assert lease_response.status_code == 200
    assert lease_response.json()["commands"][0]["command_id"] == command_id

    result_response = client.post(
        f"/api/collector/commands/{command_id}/result",
        headers=headers,
        json={"status": "applied", "result_summary": "report requested"},
    )
    assert result_response.status_code == 200

    state = client.get("/api/state", headers=headers).json()
    assert state["commands"][0]["status"] == "applied"


def test_static_index_is_served(tmp_path) -> None:
    app = create_app(db_path=tmp_path / "agent-office.sqlite", api_token="test-token")
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "Agent Office" in response.text
