from datetime import UTC, datetime

import anyio
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from agent_office.models import CommandAction, EventType, RuntimeType
from agent_office.server import WebSocketBroadcaster, create_app


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

    with client.websocket_connect("/ws?token=test-token") as websocket:
        message = websocket.receive_json()

    assert message["type"] == "state"
    assert "state" in message
    assert message["state"]["sessions"] == []


def test_websocket_broadcast_state_message_is_wrapped(tmp_path) -> None:
    app = create_app(db_path=tmp_path / "agent-office.sqlite", api_token="test-token")
    client = TestClient(app)

    with client.websocket_connect("/ws?token=test-token") as websocket:
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


def test_websocket_rejects_missing_token(tmp_path) -> None:
    app = create_app(db_path=tmp_path / "agent-office.sqlite", api_token="test-token")
    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws"):
            pass


def test_create_lease_and_complete_command(tmp_path) -> None:
    app = create_app(db_path=tmp_path / "agent-office.sqlite", api_token="test-token")
    client = TestClient(app)
    headers = {"Authorization": "Bearer test-token"}

    event_response = client.post(
        "/api/events",
        headers=headers,
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
    assert event_response.status_code == 202

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
        json={"machine_id": "machine-a", "status": "applied", "result_summary": "report requested"},
    )
    assert result_response.status_code == 200

    state = client.get("/api/state", headers=headers).json()
    assert state["commands"][0]["status"] == "applied"


def test_create_command_rejects_unsupported_session_capability(tmp_path) -> None:
    app = create_app(db_path=tmp_path / "agent-office.sqlite", api_token="test-token")
    client = TestClient(app)
    headers = {"Authorization": "Bearer test-token"}

    event_response = client.post(
        "/api/events",
        headers=headers,
        json={
            "event_id": "evt-1",
            "machine_id": "machine-a",
            "runtime_type": RuntimeType.CODEX,
            "session_id": "codex-1",
            "event_type": EventType.SESSION_STARTED,
            "timestamp": datetime(2026, 5, 26, 3, 0, tzinfo=UTC).isoformat(),
            "payload": {
                "project_name": "repo",
                "capabilities": ["request_report"],
            },
        },
    )
    assert event_response.status_code == 202

    rejected_response = client.post(
        "/api/commands",
        headers=headers,
        json={
            "target_machine_id": "machine-a",
            "target_session_id": "codex-1",
            "action": CommandAction.APPEND_PROMPT,
            "payload": {"prompt": "Continue with more detail."},
            "actor": "derek",
            "audit_metadata": {"source": "test"},
        },
    )
    assert rejected_response.status_code == 403

    allowed_response = client.post(
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
    assert allowed_response.status_code == 201


def test_create_command_rejects_unknown_session(tmp_path) -> None:
    app = create_app(db_path=tmp_path / "agent-office.sqlite", api_token="test-token")
    client = TestClient(app)

    response = client.post(
        "/api/commands",
        headers={"Authorization": "Bearer test-token"},
        json={
            "target_machine_id": "machine-a",
            "target_session_id": "missing-session",
            "action": CommandAction.REQUEST_REPORT,
            "payload": {"prompt": "Report progress."},
            "actor": "derek",
        },
    )

    assert response.status_code == 404


def test_command_result_unknown_command_returns_404(tmp_path) -> None:
    app = create_app(db_path=tmp_path / "agent-office.sqlite", api_token="test-token")
    client = TestClient(app)

    response = client.post(
        "/api/collector/commands/missing-command/result",
        headers={"Authorization": "Bearer test-token"},
        json={"machine_id": "machine-a", "status": "applied", "result_summary": "not found"},
    )

    assert response.status_code == 404


def test_command_result_rejects_non_terminal_status(tmp_path) -> None:
    app = create_app(db_path=tmp_path / "agent-office.sqlite", api_token="test-token")
    client = TestClient(app)

    response = client.post(
        "/api/collector/commands/cmd-1/result",
        headers={"Authorization": "Bearer test-token"},
        json={"machine_id": "machine-a", "status": "leased", "result_summary": "still running"},
    )

    assert response.status_code == 422


def test_command_result_requires_leased_target_machine(tmp_path) -> None:
    app = create_app(db_path=tmp_path / "agent-office.sqlite", api_token="test-token")
    client = TestClient(app)
    headers = {"Authorization": "Bearer test-token"}

    event_response = client.post(
        "/api/events",
        headers=headers,
        json={
            "event_id": "evt-1",
            "machine_id": "machine-a",
            "runtime_type": RuntimeType.CODEX,
            "session_id": "codex-1",
            "event_type": EventType.SESSION_STARTED,
            "timestamp": datetime(2026, 5, 26, 3, 0, tzinfo=UTC).isoformat(),
            "payload": {
                "project_name": "repo",
                "capabilities": ["request_report"],
            },
        },
    )
    assert event_response.status_code == 202

    create_response = client.post(
        "/api/commands",
        headers=headers,
        json={
            "target_machine_id": "machine-a",
            "target_session_id": "codex-1",
            "action": CommandAction.REQUEST_REPORT,
            "payload": {"prompt": "Report progress."},
            "actor": "derek",
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

    wrong_machine_response = client.post(
        f"/api/collector/commands/{command_id}/result",
        headers=headers,
        json={"machine_id": "machine-b", "status": "applied", "result_summary": "wrong collector"},
    )
    assert wrong_machine_response.status_code == 404

    first_response = client.post(
        f"/api/collector/commands/{command_id}/result",
        headers=headers,
        json={"machine_id": "machine-a", "status": "applied", "result_summary": "report requested"},
    )
    assert first_response.status_code == 200

    second_response = client.post(
        f"/api/collector/commands/{command_id}/result",
        headers=headers,
        json={"machine_id": "machine-a", "status": "failed", "result_summary": "stale retry"},
    )
    assert second_response.status_code == 404


def test_broadcast_disconnects_socket_after_send_error() -> None:
    class BrokenSocket:
        def __init__(self) -> None:
            self.send_count = 0

        async def send_json(self, payload: dict[str, object]) -> None:
            self.send_count += 1
            raise ValueError("socket closed")

    broadcaster = WebSocketBroadcaster()
    socket = BrokenSocket()
    broadcaster._sockets.add(socket)  # type: ignore[arg-type]

    anyio.run(broadcaster.broadcast, {"type": "state"})
    anyio.run(broadcaster.broadcast, {"type": "state"})

    assert socket.send_count == 1


def test_static_index_is_served(tmp_path) -> None:
    app = create_app(db_path=tmp_path / "agent-office.sqlite", api_token="test-token")
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "Agent Office" in response.text


def test_static_office_assets_are_served(tmp_path) -> None:
    app = create_app(db_path=tmp_path / "agent-office.sqlite", api_token="test-token")
    client = TestClient(app)

    response = client.get("/assets/office/manifest.json")

    assert response.status_code == 200
    assert "calf" in response.text
    assert "pony" in response.text
