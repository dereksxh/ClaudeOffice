from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from agent_office.models import CommandAction, CommandStatus, ControlCommand, EventRecord
from agent_office.projector import project_state
from agent_office.storage import (
    complete_command,
    create_command,
    init_db,
    insert_event,
    lease_commands,
    list_commands,
    list_events,
)

WEB_DIR = Path(__file__).parent / "web"


class CreateCommandRequest(BaseModel):
    target_machine_id: str
    target_session_id: str
    target_agent_id: str | None = None
    action: CommandAction
    payload: dict[str, Any] = Field(default_factory=dict)
    actor: str
    audit_metadata: dict[str, Any] = Field(default_factory=dict)


class LeaseCommandsRequest(BaseModel):
    machine_id: str
    limit: int = Field(default=10, gt=0, le=100)


class CommandResultRequest(BaseModel):
    status: Literal[CommandStatus.APPLIED, CommandStatus.FAILED]
    result_summary: str


class WebSocketBroadcaster:
    def __init__(self) -> None:
        self._sockets: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._sockets.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self._sockets.discard(websocket)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        disconnected: list[WebSocket] = []
        for websocket in list(self._sockets):
            try:
                await websocket.send_json(payload)
            except Exception:
                disconnected.append(websocket)
        for websocket in disconnected:
            self.disconnect(websocket)


def create_app(db_path: str | Path, api_token: str) -> FastAPI:
    app = FastAPI(title="Agent Office")
    db_file = Path(db_path)
    broadcaster = WebSocketBroadcaster()

    def get_conn() -> sqlite3.Connection:
        conn = sqlite3.connect(db_file)
        init_db(conn)
        return conn

    def authorize(authorization: str | None = Header(default=None)) -> None:
        if authorization != f"Bearer {api_token}":
            raise HTTPException(status_code=401, detail="Unauthorized")

    def current_state() -> dict[str, Any]:
        with get_conn() as conn:
            state = project_state(
                list_events(conn),
                list_commands(conn),
                now=datetime.now(UTC),
            )
        return state.model_dump(mode="json")

    def state_message() -> dict[str, Any]:
        return {"type": "state", "state": current_state()}

    async def broadcast_state() -> None:
        await broadcaster.broadcast(state_message())

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        path = WEB_DIR / "index.html"
        if path.exists():
            return HTMLResponse(path.read_text(encoding="utf-8"))
        return HTMLResponse("<!doctype html><title>Agent Office</title><h1>Agent Office</h1>")

    @app.get("/app.js")
    def app_js() -> Response:
        return Response((WEB_DIR / "app.js").read_text(encoding="utf-8"), media_type="text/javascript")

    @app.get("/styles.css")
    def styles_css() -> Response:
        return Response((WEB_DIR / "styles.css").read_text(encoding="utf-8"), media_type="text/css")

    @app.post("/api/events", status_code=202, dependencies=[Depends(authorize)])
    async def ingest_event(event: EventRecord) -> dict[str, bool]:
        with get_conn() as conn:
            inserted = insert_event(conn, event)
        await broadcast_state()
        return {"inserted": inserted}

    @app.get("/api/state", dependencies=[Depends(authorize)])
    def get_state() -> dict[str, Any]:
        return current_state()

    @app.post("/api/commands", status_code=201, dependencies=[Depends(authorize)])
    async def post_command(request: CreateCommandRequest) -> ControlCommand:
        command = ControlCommand(
            command_id=f"cmd-{uuid4()}",
            target_machine_id=request.target_machine_id,
            target_session_id=request.target_session_id,
            target_agent_id=request.target_agent_id,
            action=request.action,
            payload=request.payload,
            actor=request.actor,
            audit_metadata=request.audit_metadata,
        )
        with get_conn() as conn:
            create_command(conn, command)
        await broadcast_state()
        return command

    @app.post("/api/collector/commands/lease", dependencies=[Depends(authorize)])
    def lease_collector_commands(request: LeaseCommandsRequest) -> dict[str, list[ControlCommand]]:
        with get_conn() as conn:
            commands = lease_commands(
                conn,
                machine_id=request.machine_id,
                now=datetime.now(UTC),
                limit=request.limit,
            )
        return {"commands": commands}

    @app.post("/api/collector/commands/{command_id}/result", dependencies=[Depends(authorize)])
    async def post_command_result(command_id: str, request: CommandResultRequest) -> dict[str, str]:
        with get_conn() as conn:
            updated = complete_command(
                conn,
                command_id=command_id,
                status=request.status,
                result_summary=request.result_summary,
                completed_at=datetime.now(UTC),
            )
        if not updated:
            raise HTTPException(status_code=404, detail="Command not found")
        await broadcast_state()
        return {"status": "accepted"}

    @app.websocket("/ws")
    async def websocket_state(websocket: WebSocket) -> None:
        if websocket.query_params.get("token") != api_token:
            await websocket.close(code=1008)
            return
        await broadcaster.connect(websocket)
        try:
            await websocket.send_json(state_message())
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            broadcaster.disconnect(websocket)

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Agent Office API server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--db-path", default=os.environ.get("AGENT_OFFICE_DB", "agent-office.sqlite"))
    args = parser.parse_args()
    token = os.environ.get("AGENT_OFFICE_TOKEN", "dev-token")
    uvicorn.run(create_app(db_path=args.db_path, api_token=token), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
