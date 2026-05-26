import hashlib
from datetime import UTC, datetime

from agent_office.collector.adapters.claude_code import map_claude_hook_event
from agent_office.collector.adapters.codex import map_codex_hook_event
from agent_office.collector.adapters.hermes import map_hermes_snapshot
from agent_office.models import Capability, EventType, RuntimeType


def test_codex_user_prompt_maps_to_session_started_or_updated_event() -> None:
    event = map_codex_hook_event(
        machine_id="machine-a",
        hook_event_name="UserPromptSubmit",
        payload={
            "session_id": "codex-1",
            "cwd": "/repo",
            "model": "gpt-5",
            "prompt": "Build Agent Office",
        },
        timestamp=datetime(2026, 5, 26, 3, 0, tzinfo=UTC),
    )

    assert event.runtime_type == RuntimeType.CODEX
    assert event.event_type == EventType.USER_PROMPT
    assert event.session_id == "codex-1"
    assert event.payload["current_task"] == "Build Agent Office"
    assert Capability.REQUEST_REPORT.value in event.payload["capabilities"]


def test_claude_pascal_case_user_prompt_maps_to_user_prompt_event() -> None:
    event = map_claude_hook_event(
        machine_id="machine-a",
        hook_event_name="UserPromptSubmit",
        payload={
            "session_id": "claude-1",
            "cwd": "/repo",
            "prompt": "Build Agent Office",
        },
        timestamp=datetime(2026, 5, 26, 3, 0, tzinfo=UTC),
    )

    assert event.runtime_type == RuntimeType.CLAUDE_CODE
    assert event.event_type == EventType.USER_PROMPT
    assert event.session_id == "claude-1"
    assert event.payload["current_task"] == "Build Agent Office"
    assert Capability.REQUEST_REPORT.value in event.payload["capabilities"]


def test_claude_repeated_user_prompts_have_distinct_event_ids() -> None:
    first = map_claude_hook_event(
        machine_id="machine-a",
        hook_event_name="UserPromptSubmit",
        payload={"session_id": "claude-1", "prompt": "First task"},
        timestamp=datetime(2026, 5, 26, 3, 0, tzinfo=UTC),
    )
    second = map_claude_hook_event(
        machine_id="machine-a",
        hook_event_name="UserPromptSubmit",
        payload={"session_id": "claude-1", "prompt": "Second task"},
        timestamp=datetime(2026, 5, 26, 3, 1, tzinfo=UTC),
    )

    assert first.event_id != second.event_id


def test_claude_identical_user_prompts_at_different_times_have_distinct_event_ids() -> None:
    first = map_claude_hook_event(
        machine_id="machine-a",
        hook_event_name="UserPromptSubmit",
        payload={"session_id": "claude-1", "prompt": "continue"},
        timestamp=datetime(2026, 5, 26, 3, 0, tzinfo=UTC),
    )
    second = map_claude_hook_event(
        machine_id="machine-a",
        hook_event_name="UserPromptSubmit",
        payload={"session_id": "claude-1", "prompt": "continue"},
        timestamp=datetime(2026, 5, 26, 3, 1, tzinfo=UTC),
    )
    retry = map_claude_hook_event(
        machine_id="machine-a",
        hook_event_name="UserPromptSubmit",
        payload={"session_id": "claude-1", "prompt": "continue"},
        timestamp=datetime(2026, 5, 26, 3, 0, tzinfo=UTC),
    )

    assert first.event_id != second.event_id
    assert first.event_id == retry.event_id


def test_codex_tool_use_id_disambiguates_tool_events() -> None:
    first = map_codex_hook_event(
        machine_id="machine-a",
        hook_event_name="PreToolUse",
        payload={
            "session_id": "codex-1",
            "turn_id": "turn-1",
            "tool_use_id": "tool-1",
            "tool_name": "Bash",
        },
        timestamp=datetime(2026, 5, 26, 3, 0, tzinfo=UTC),
    )
    second = map_codex_hook_event(
        machine_id="machine-a",
        hook_event_name="PreToolUse",
        payload={
            "session_id": "codex-1",
            "turn_id": "turn-1",
            "tool_use_id": "tool-2",
            "tool_name": "Bash",
        },
        timestamp=datetime(2026, 5, 26, 3, 1, tzinfo=UTC),
    )

    assert first.event_id != second.event_id


def test_claude_task_tool_maps_to_agent_started_event() -> None:
    event = map_claude_hook_event(
        machine_id="machine-a",
        hook_event_name="pre_tool_use",
        payload={
            "session_id": "claude-1",
            "tool_name": "Task",
            "tool_use_id": "tool-1",
            "cwd": "/repo",
            "tool_input": {
                "description": "Review storage",
                "prompt": "Review storage module",
                "subagent_type": "reviewer",
            },
        },
        timestamp=datetime(2026, 5, 26, 3, 0, tzinfo=UTC),
    )

    assert event.runtime_type == RuntimeType.CLAUDE_CODE
    assert event.event_type == EventType.AGENT_STARTED
    assert event.agent_id == "subagent_tool-1"
    expected_event_id = "claude-" + hashlib.sha256(
        "machine-a:claude-1:pre_tool_use:tool-1:subagent_tool-1".encode()
    ).hexdigest()[:24]
    assert event.event_id == expected_event_id
    assert event.payload["agent_type"] == "reviewer"
    assert event.payload["task_description"] == "Review storage module"


def test_hermes_snapshot_maps_to_session_update() -> None:
    event = map_hermes_snapshot(
        machine_id="machine-a",
        snapshot={
            "session_id": "hermes-1",
            "project_name": "ticketops",
            "status": "working",
            "summary": "processing gateway request",
            "can_accept_prompt": False,
        },
        timestamp=datetime(2026, 5, 26, 3, 0, tzinfo=UTC),
    )

    assert event.runtime_type == RuntimeType.HERMES
    assert event.event_type == EventType.SESSION_UPDATED
    assert event.payload["progress_summary"] == "processing gateway request"
    assert Capability.REQUEST_REPORT.value in event.payload["capabilities"]
    assert Capability.APPEND_PROMPT.value not in event.payload["capabilities"]
