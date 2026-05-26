from __future__ import annotations

from dataclasses import dataclass

import httpx
from fastapi.testclient import TestClient

from agent_office.models import CommandStatus, ControlCommand, EventRecord


@dataclass
class CollectorClient:
    base_url: str
    token: str
    _test_client: TestClient | None = None

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")

    @classmethod
    def for_test_client(cls, test_client: TestClient, token: str) -> CollectorClient:
        return cls(base_url="http://testserver", token=token, _test_client=test_client)

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def post_event(self, event: EventRecord) -> None:
        payload = event.model_dump(mode="json")
        if self._test_client:
            response = self._test_client.post("/api/events", headers=self.headers, json=payload)
        else:
            response = httpx.post(f"{self.base_url}/api/events", headers=self.headers, json=payload, timeout=5)
        response.raise_for_status()

    def lease_commands(self, machine_id: str, limit: int = 10) -> list[ControlCommand]:
        payload = {"machine_id": machine_id, "limit": limit}
        if self._test_client:
            response = self._test_client.post("/api/collector/commands/lease", headers=self.headers, json=payload)
        else:
            response = httpx.post(
                f"{self.base_url}/api/collector/commands/lease",
                headers=self.headers,
                json=payload,
                timeout=5,
            )
        response.raise_for_status()
        return [ControlCommand(**item) for item in response.json()["commands"]]

    def post_command_result(
        self,
        command_id: str,
        machine_id: str,
        status: CommandStatus,
        result_summary: str,
    ) -> None:
        payload = {"machine_id": machine_id, "status": status.value, "result_summary": result_summary}
        if self._test_client:
            response = self._test_client.post(
                f"/api/collector/commands/{command_id}/result",
                headers=self.headers,
                json=payload,
            )
        else:
            response = httpx.post(
                f"{self.base_url}/api/collector/commands/{command_id}/result",
                headers=self.headers,
                json=payload,
                timeout=5,
            )
        response.raise_for_status()
