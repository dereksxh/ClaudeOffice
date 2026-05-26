from datetime import UTC, datetime
from argparse import Namespace
import json

import pytest
from fastapi.testclient import TestClient

from agent_office.collector.adapters.base import AdapterCommandResult
from agent_office.collector.adapters.claude_code import ClaudeHookLogAdapter
from agent_office.collector.adapters.codex import CodexHookLogAdapter, CodexSessionDirectoryAdapter
from agent_office.collector.adapters.fake import FakeAdapter
from agent_office.collector.adapters.hermes import HermesGatewayStateAdapter, HermesSnapshotFileAdapter
from agent_office.collector.adapters.usage import ClaudeCodeUsageAdapter
from agent_office.collector.client import CollectorClient
from agent_office.collector import runner
from agent_office.collector.runner import build_adapters, collect_once
from agent_office.models import CommandAction, ControlCommand, EventType, RuntimeType
from agent_office.server import create_app


def test_collector_client_normalizes_trailing_slash_base_url(monkeypatch) -> None:
    posted_urls: list[str] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    def fake_post(url, **kwargs):
        posted_urls.append(url)
        return FakeResponse()

    monkeypatch.setattr("agent_office.collector.client.httpx.post", fake_post)
    client = CollectorClient(base_url="http://central/", token="test-token")
    event = FakeAdapter(machine_id="machine-a", hostname="worker-a").snapshot_events(
        now=datetime(2026, 5, 26, 3, 0, tzinfo=UTC)
    )[0]

    client.post_event(event)

    assert posted_urls == ["http://central/api/events"]


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


def test_collector_posts_machine_heartbeat_for_read_only_adapters(tmp_path) -> None:
    class ReadOnlyAdapter:
        machine_id = "machine-a"
        runtime_type = RuntimeType.CODEX

        def snapshot_events(self, now):
            return []

        def apply_command(self, command):
            return AdapterCommandResult(False, "read-only")

    app = create_app(db_path=tmp_path / "agent-office.sqlite", api_token="test-token")
    test_client = TestClient(app)
    collector_client = CollectorClient.for_test_client(test_client, token="test-token")

    collect_once(
        client=collector_client,
        adapters=[ReadOnlyAdapter()],
        now=datetime.now(UTC),
    )

    state = test_client.get(
        "/api/state",
        headers={"Authorization": "Bearer test-token"},
    ).json()
    assert state["machines"][0]["machine_id"] == "machine-a"
    assert state["machines"][0]["health"] == "online"
    assert state["machines"][0]["runtime_inventory"] == ["codex"]


def test_collector_leases_and_applies_supported_command(tmp_path) -> None:
    app = create_app(db_path=tmp_path / "agent-office.sqlite", api_token="test-token")
    test_client = TestClient(app)
    collector_client = CollectorClient.for_test_client(test_client, token="test-token")
    adapter = FakeAdapter(machine_id="machine-a", hostname="worker-a")

    collect_once(
        client=collector_client,
        adapters=[adapter],
        now=datetime(2026, 5, 26, 3, 0, tzinfo=UTC),
    )

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


def test_collector_does_not_queue_unsupported_command(tmp_path) -> None:
    app = create_app(db_path=tmp_path / "agent-office.sqlite", api_token="test-token")
    test_client = TestClient(app)
    collector_client = CollectorClient.for_test_client(test_client, token="test-token")
    adapter = FakeAdapter(machine_id="machine-a", hostname="worker-a")

    collect_once(
        client=collector_client,
        adapters=[adapter],
        now=datetime(2026, 5, 26, 3, 0, tzinfo=UTC),
    )

    create_response = test_client.post(
        "/api/commands",
        headers={"Authorization": "Bearer test-token"},
        json={
            "target_machine_id": "machine-a",
            "target_session_id": "fake-session",
            "action": CommandAction.APPEND_PROMPT,
            "payload": {"prompt": "Add this."},
            "actor": "derek",
        },
    )
    assert create_response.status_code == 403
    assert adapter.applied_commands == []


def test_runner_loop_continues_after_collect_once_error(monkeypatch, capsys) -> None:
    sleep_calls: list[float] = []

    def fake_collect_once(client, adapters):
        raise RuntimeError("central unavailable")

    def fake_sleep(interval):
        sleep_calls.append(interval)
        raise KeyboardInterrupt

    monkeypatch.setattr(runner, "collect_once", fake_collect_once)
    monkeypatch.setattr(runner.time, "sleep", fake_sleep)
    monkeypatch.setenv("AGENT_OFFICE_TOKEN", "test-token")
    monkeypatch.setattr("sys.argv", ["collector", "--interval", "0.25"])

    with pytest.raises(KeyboardInterrupt):
        runner.main()

    captured = capsys.readouterr()
    assert "collector iteration failed: central unavailable" in captured.err
    assert sleep_calls == [0.25]


def test_runner_builds_configured_runtime_adapters_and_fake_is_opt_in(tmp_path) -> None:
    codex_log = tmp_path / "codex.jsonl"
    claude_log = tmp_path / "claude.jsonl"
    hermes_snapshot = tmp_path / "hermes.json"
    outbox_dir = tmp_path / "outbox"

    args = Namespace(
        machine_id="machine-a",
        hostname="worker-a",
        codex_hook_log=str(codex_log),
        codex_sessions_dir=None,
        claude_hook_log=str(claude_log),
        hermes_snapshot=str(hermes_snapshot),
        hermes_home=None,
        claude_projects_dir=None,
        command_outbox_dir=str(outbox_dir),
        enable_fake=False,
    )

    adapters = build_adapters(args)

    assert [type(adapter) for adapter in adapters] == [
        CodexHookLogAdapter,
        ClaudeHookLogAdapter,
        HermesSnapshotFileAdapter,
    ]

    fake_args = Namespace(**{**vars(args), "enable_fake": True})
    fake_adapters = build_adapters(fake_args)

    assert any(isinstance(adapter, FakeAdapter) for adapter in fake_adapters)


def test_runner_builds_local_discovery_adapters(tmp_path) -> None:
    codex_sessions = tmp_path / "codex-sessions"
    hermes_home = tmp_path / "hermes"
    args = Namespace(
        machine_id="machine-a",
        hostname="worker-a",
        codex_hook_log=None,
        codex_sessions_dir=str(codex_sessions),
        claude_hook_log=None,
        hermes_snapshot=None,
        hermes_home=str(hermes_home),
        claude_projects_dir=None,
        command_outbox_dir=None,
        enable_fake=False,
    )

    adapters = build_adapters(args)

    assert [type(adapter) for adapter in adapters] == [
        CodexSessionDirectoryAdapter,
        HermesGatewayStateAdapter,
    ]


def test_runner_builds_claude_usage_adapter(tmp_path) -> None:
    args = Namespace(
        machine_id="machine-a",
        hostname="worker-a",
        codex_hook_log=None,
        codex_sessions_dir=None,
        claude_hook_log=None,
        hermes_snapshot=None,
        hermes_home=None,
        claude_projects_dir=str(tmp_path / "claude-projects"),
        command_outbox_dir=None,
        enable_fake=False,
    )

    adapters = build_adapters(args)

    assert [type(adapter) for adapter in adapters] == [ClaudeCodeUsageAdapter]


def test_codex_hook_log_adapter_maps_events_and_writes_command_outbox(tmp_path) -> None:
    hook_log = tmp_path / "codex.jsonl"
    outbox = tmp_path / "codex-commands.jsonl"
    hook_log.write_text(
        json.dumps(
            {
                "hook_event_name": "UserPromptSubmit",
                "timestamp": "2026-05-26T03:00:00+00:00",
                "payload": {
                    "session_id": "codex-1",
                    "cwd": "/repo",
                    "model": "gpt-5",
                    "prompt": "Build Agent Office",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    adapter = CodexHookLogAdapter(
        machine_id="machine-a",
        hook_log_path=hook_log,
        command_outbox_path=outbox,
    )

    events = adapter.snapshot_events(datetime(2026, 5, 26, 3, 1, tzinfo=UTC))

    assert events[0].runtime_type == RuntimeType.CODEX
    assert events[0].event_type == EventType.USER_PROMPT
    assert events[0].session_id == "codex-1"

    result = adapter.apply_command(
        ControlCommand(
            command_id="cmd-1",
            target_machine_id="machine-a",
            target_session_id="codex-1",
            action=CommandAction.CONTINUE,
            actor="derek",
        )
    )

    assert result.applied is True
    outbox_record = json.loads(outbox.read_text(encoding="utf-8").strip())
    assert outbox_record["command_id"] == "cmd-1"
    assert outbox_record["action"] == "continue"


def test_codex_session_directory_adapter_maps_recent_session_files(tmp_path) -> None:
    sessions_dir = tmp_path / "sessions"
    session_file = sessions_dir / "2026" / "05" / "26" / "rollout.jsonl"
    session_file.parent.mkdir(parents=True)
    session_file.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-05-26T03:00:00Z",
                        "type": "session_meta",
                        "payload": {
                            "id": "codex-session-1",
                            "cwd": "/repo",
                            "cli_version": "0.133.0",
                            "model": "gpt-5.4",
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-05-26T03:01:00Z",
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": "Connect local Codex"}],
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-05-26T03:02:00Z",
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "Inspecting session files"}],
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    adapter = CodexSessionDirectoryAdapter(
        machine_id="machine-a",
        sessions_dir=sessions_dir,
        max_sessions=5,
        active_ttl_seconds=3600,
    )

    events = adapter.snapshot_events(datetime(2026, 5, 26, 3, 3, tzinfo=UTC))

    assert len(events) == 2
    assert events[0].runtime_type == RuntimeType.CODEX
    assert events[0].session_id == "codex-session-1"
    assert events[0].payload["project_name"] == "repo"
    assert events[0].payload["current_task"] == "Connect local Codex"
    assert events[0].payload["progress_summary"] == "Inspecting session files"
    assert events[0].payload["status"] == "working"
    assert events[0].timestamp == datetime(2026, 5, 26, 3, 3, tzinfo=UTC)
    assert events[1].event_type == EventType.USAGE_SNAPSHOT
    assert events[1].payload["total_tokens"] == 0

    next_events = adapter.snapshot_events(datetime(2026, 5, 26, 3, 4, tzinfo=UTC))

    assert next_events[0].event_id != events[0].event_id


def test_codex_session_directory_adapter_emits_token_usage_snapshot(tmp_path) -> None:
    sessions_dir = tmp_path / "sessions"
    session_file = sessions_dir / "2026" / "05" / "26" / "rollout.jsonl"
    session_file.parent.mkdir(parents=True)
    session_file.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-05-26T03:00:00Z",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "total_token_usage": {
                                    "input_tokens": 10,
                                    "cached_input_tokens": 2,
                                    "output_tokens": 3,
                                    "reasoning_output_tokens": 1,
                                    "total_tokens": 13,
                                }
                            },
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-05-26T03:01:00Z",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "total_token_usage": {
                                    "input_tokens": 20,
                                    "cached_input_tokens": 4,
                                    "output_tokens": 6,
                                    "reasoning_output_tokens": 2,
                                    "total_tokens": 26,
                                }
                            },
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    adapter = CodexSessionDirectoryAdapter(machine_id="machine-a", sessions_dir=sessions_dir, max_sessions=5)

    events = adapter.snapshot_events(datetime(2026, 5, 26, 3, 2, tzinfo=UTC))
    usage = events[-1]

    assert usage.event_type == EventType.USAGE_SNAPSHOT
    assert usage.payload["input_tokens"] == 20
    assert usage.payload["cached_input_tokens"] == 4
    assert usage.payload["output_tokens"] == 6
    assert usage.payload["reasoning_output_tokens"] == 2
    assert usage.payload["total_tokens"] == 26
    assert usage.payload["request_count"] == 2
    assert usage.payload["session_count"] == 1


def test_codex_usage_snapshot_includes_periods_models_and_credit_cost(tmp_path) -> None:
    sessions_dir = tmp_path / "sessions"
    session_file = sessions_dir / "2026" / "05" / "26" / "rollout.jsonl"
    session_file.parent.mkdir(parents=True)
    session_file.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-05-25T00:59:00Z",
                        "type": "session_meta",
                        "payload": {"id": "codex-session-1", "model": "gpt-5.4"},
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-05-25T01:00:00Z",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "total_token_usage": {
                                    "input_tokens": 1_000_000,
                                    "cached_input_tokens": 0,
                                    "output_tokens": 0,
                                    "total_tokens": 1_000_000,
                                },
                                "last_token_usage": {
                                    "input_tokens": 1_000_000,
                                    "cached_input_tokens": 0,
                                    "output_tokens": 0,
                                    "total_tokens": 1_000_000,
                                },
                            },
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-05-25T17:00:00Z",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "total_token_usage": {
                                    "input_tokens": 2_000_000,
                                    "cached_input_tokens": 200_000,
                                    "output_tokens": 100_000,
                                    "total_tokens": 2_100_000,
                                },
                                "last_token_usage": {
                                    "input_tokens": 1_000_000,
                                    "cached_input_tokens": 200_000,
                                    "output_tokens": 100_000,
                                    "total_tokens": 1_100_000,
                                },
                            },
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    adapter = CodexSessionDirectoryAdapter(machine_id="machine-a", sessions_dir=sessions_dir, max_sessions=5)

    events = adapter.snapshot_events(datetime(2026, 5, 26, 3, 0, tzinfo=UTC))
    usage = events[-1].payload

    today = next(period for period in usage["periods"] if period["period"] == "today")
    week = next(period for period in usage["periods"] if period["period"] == "week")
    model = usage["model_breakdown"][0]
    assert usage["billable_unit"] == "credits"
    assert usage["billable_amount"] == pytest.approx(151.25)
    assert today["billable_amount"] == pytest.approx(88.75)
    assert today["total_tokens"] == 1_100_000
    assert week["budget_amount"] == 5000
    assert week["billable_amount"] == pytest.approx(151.25)
    assert week["request_count"] == 2
    assert model["model"] == "gpt-5.4"
    assert model["billable_amount"] == pytest.approx(151.25)


def test_claude_usage_adapter_deduplicates_message_usage(tmp_path) -> None:
    projects_dir = tmp_path / "projects"
    project_dir = projects_dir / "repo"
    project_dir.mkdir(parents=True)
    record = {
        "timestamp": "2026-05-26T03:00:00Z",
        "requestId": "req-1",
        "message": {
            "id": "msg-1",
            "model": "claude-sonnet-4-6",
            "usage": {
                "input_tokens": 10,
                "cache_creation_input_tokens": 20,
                "cache_read_input_tokens": 30,
                "output_tokens": 40,
            },
        },
    }
    (project_dir / "session.jsonl").write_text(
        json.dumps(record) + "\n" + json.dumps(record) + "\n",
        encoding="utf-8",
    )
    adapter = ClaudeCodeUsageAdapter(machine_id="machine-a", projects_dir=projects_dir)

    events = adapter.snapshot_events(datetime(2026, 5, 26, 3, 1, tzinfo=UTC))

    assert len(events) == 1
    assert events[0].event_type == EventType.USAGE_SNAPSHOT
    assert events[0].runtime_type == RuntimeType.CLAUDE_CODE
    assert events[0].payload["input_tokens"] == 10
    assert events[0].payload["cache_creation_input_tokens"] == 20
    assert events[0].payload["cache_read_input_tokens"] == 30
    assert events[0].payload["output_tokens"] == 40
    assert events[0].payload["total_tokens"] == 100
    assert events[0].payload["request_count"] == 1


def test_claude_usage_snapshot_includes_periods_models_and_usd_cost(tmp_path) -> None:
    projects_dir = tmp_path / "projects"
    project_dir = projects_dir / "repo"
    project_dir.mkdir(parents=True)
    records = [
        {
            "timestamp": "2026-05-25T01:00:00Z",
            "requestId": "req-week",
            "message": {
                "id": "msg-week",
                "model": "claude-sonnet-4-6",
                "usage": {
                    "input_tokens": 1_000_000,
                    "cache_creation_input_tokens": 1_000_000,
                    "cache_read_input_tokens": 500_000,
                    "output_tokens": 100_000,
                    "cache_creation": {
                        "ephemeral_5m_input_tokens": 0,
                        "ephemeral_1h_input_tokens": 1_000_000,
                    },
                },
            },
        },
        {
            "timestamp": "2026-05-25T17:00:00Z",
            "requestId": "req-today",
            "message": {
                "id": "msg-today",
                "model": "claude-haiku-4-5-20251001",
                "usage": {
                    "input_tokens": 1_000_000,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                    "output_tokens": 1_000_000,
                },
            },
        },
    ]
    (project_dir / "session.jsonl").write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    adapter = ClaudeCodeUsageAdapter(machine_id="machine-a", projects_dir=projects_dir)

    events = adapter.snapshot_events(datetime(2026, 5, 26, 3, 0, tzinfo=UTC))
    usage = events[0].payload

    today = next(period for period in usage["periods"] if period["period"] == "today")
    week = next(period for period in usage["periods"] if period["period"] == "week")
    models = {item["model"]: item for item in usage["model_breakdown"]}
    assert usage["billable_unit"] == "usd"
    assert usage["billable_amount"] == pytest.approx(16.65)
    assert today["billable_amount"] == pytest.approx(6.0)
    assert week["billable_amount"] == pytest.approx(16.65)
    assert models["claude-sonnet-4-6"]["billable_amount"] == pytest.approx(10.65)
    assert models["claude-haiku-4-5-20251001"]["billable_amount"] == pytest.approx(6.0)


def test_hermes_snapshot_file_adapter_maps_snapshot_file(tmp_path) -> None:
    snapshot_path = tmp_path / "hermes.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "session_id": "hermes-1",
                "project_name": "ticketops",
                "status": "working",
                "summary": "processing request",
                "can_accept_prompt": True,
            }
        ),
        encoding="utf-8",
    )
    adapter = HermesSnapshotFileAdapter(
        machine_id="machine-a",
        snapshot_path=snapshot_path,
        command_outbox_path=tmp_path / "hermes-commands.jsonl",
    )

    events = adapter.snapshot_events(datetime(2026, 5, 26, 3, 0, tzinfo=UTC))

    assert events[0].runtime_type == RuntimeType.HERMES
    assert events[0].session_id == "hermes-1"
    assert events[0].payload["progress_summary"] == "processing request"


def test_hermes_gateway_state_adapter_maps_root_and_profiles(tmp_path) -> None:
    hermes_home = tmp_path / "hermes"
    (hermes_home / "profiles" / "luoluo").mkdir(parents=True)
    (hermes_home / "gateway_state.json").write_text(
        json.dumps(
            {
                "pid": 6208,
                "gateway_state": "running",
                "active_agents": 0,
                "platforms": {"api_server": {"state": "connected"}},
                "updated_at": "2026-05-26T03:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    (hermes_home / "profiles" / "luoluo" / "gateway_state.json").write_text(
        json.dumps(
            {
                "pid": 115239,
                "gateway_state": "running",
                "active_agents": 2,
                "platforms": {"api_server": {"state": "connected"}},
                "updated_at": "2026-05-26T03:01:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    adapter = HermesGatewayStateAdapter(machine_id="machine-a", hermes_home=hermes_home)

    events = adapter.snapshot_events(datetime(2026, 5, 26, 3, 2, tzinfo=UTC))

    assert [event.session_id for event in events] == ["hermes:default", "hermes:luoluo"]
    assert events[0].payload["status"] == "idle"
    assert events[1].payload["status"] == "working"
    assert events[1].payload["project_name"] == "Hermes luoluo"
    assert "pid=115239" in events[1].payload["progress_summary"]
    assert events[0].timestamp == datetime(2026, 5, 26, 3, 2, tzinfo=UTC)
    assert events[1].timestamp == datetime(2026, 5, 26, 3, 2, tzinfo=UTC)

    next_events = adapter.snapshot_events(datetime(2026, 5, 26, 3, 3, tzinfo=UTC))

    assert next_events[0].event_id != events[0].event_id
