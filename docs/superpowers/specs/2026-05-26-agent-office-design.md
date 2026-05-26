# Agent Office Design

Date: 2026-05-26
Status: approved for implementation planning

## Summary

Agent Office is an internal operations console for Codex CLI, Claude Code, and Hermes/self-hosted agents. It should show local and remote agent activity, expose progress and blocker signals, and allow low-risk intervention through audited control actions.

The chosen direction is a new operations-console architecture with a visual strategy inspired by `claude-office`: build the control model, collector protocol, audit trail, and dense console UI first; add Office/Building as a second projection of the same backend state.

## Confirmed Scope

MVP includes:

- Central service for event ingestion, state projection, command queue, audit, and WebSocket updates.
- Lightweight collector on each machine, using outbound-only communication to central.
- Runtime adapters for Codex CLI, Claude Code, and Hermes/self-hosted agents.
- Capability-based action gating per runtime/session.
- Three safe control actions: `append_prompt`, `request_report`, and `continue`.
- Default dense operations console plus a simple Office/Building projection.
- Shared token authentication for self-hosted/internal use.

MVP excludes:

- kill/restart/pause controls.
- RBAC, mTLS, per-machine certificates.
- Deep transcript replay/search.
- Full pixel-art animation parity with `claude-office`.

## Upstream Reference

`paulrobello/claude-office` validates the event-to-state-to-WebSocket pattern:

```text
runtime hooks/plugin
-> backend event ingestion
-> state machine / persistence
-> WebSocket
-> visual frontend
```

What we keep:

- Runtime-specific adapters should map native events into one normalized event model.
- Backend state is the source of truth.
- Frontend views render projected state rather than parsing runtime files directly.
- Office/Building can be a useful situational-awareness view.

What we avoid:

- Basing the core data model on animation state.
- Treating Claude Code as the only first-class runtime.
- Bolting remote control, command leasing, and audit onto a game-oriented state machine.

Reference links:

- `claude-office`: https://github.com/paulrobello/claude-office
- Codex hooks documentation: https://developers.openai.com/codex/hooks
- Claude Code hooks documentation: https://code.claude.com/docs/en/hooks

## Architecture

```text
Runtime hooks / logs / probes
  -> Machine collector
  -> Central event ingestion
  -> Append-only event store
  -> State projector
  -> WebSocket
  -> Console UI / Office UI

Control UI
  -> Central command queue
  -> Collector command poll/lease
  -> Runtime adapter action
  -> Command result event
  -> Audit log + projected state update
```

### Machine Collector

Each machine runs `agent-office-collector`.

Responsibilities:

- Emit heartbeats with hostname, labels, collector version, health, and runtime inventory.
- Discover local Codex, Claude Code, and Hermes sessions.
- Receive native runtime events through hooks, logs, APIs, and lightweight probes.
- Normalize events into the internal event schema.
- Buffer events locally during network failures and replay them later.
- Poll central for commands targeted at this machine/session.
- Execute commands through runtime adapters and report results.

Central does not SSH into remote machines and does not directly read remote files.

### Runtime Adapters

Adapters are capability-driven. Each adapter declares which actions are available for each runtime/session. The UI only shows supported actions.

Codex adapter:

- Uses Codex hooks for lifecycle, prompt, tool, subagent, and stop events when available.
- Uses local Codex history/log/state as cold-start or recovery sources.
- Uses process probes only as supporting signals.

Claude Code adapter:

- Uses Claude Code hooks and JSONL transcript metadata.
- Maps main sessions and subagents into the shared session/agent model.
- Uses transcript paths and native subagent IDs as source references when available.

Hermes adapter:

- Uses Hermes gateway/API/logs and process/port status.
- Starts with best-effort observation plus any reliable API-based actions.
- Does not write to arbitrary process stdin unless the adapter explicitly supports that transport.

### Central Service

Responsibilities:

- `POST /api/events`: authenticated event ingestion.
- `POST /api/commands`: create an audited control command.
- `POST /api/commands/lease`: collectors lease eligible commands.
- `POST /api/commands/{id}/result`: collectors report command outcomes.
- Query APIs for machines, sessions, agents, events, and command history.
- WebSocket stream for projected state and event updates.
- Deterministic state projection from append-only events.

### Web UI

Default control console:

- Machine/runtime filters.
- Session table sorted by freshness, status, runtime, and machine.
- Detail panel for selected session.
- Timeline of events, tools, prompts, command history, and command results.
- Action drawer gated by selected target capabilities.

Office/Building view:

- Renders machines as buildings/floors/rooms.
- Renders sessions/agents as desks or people.
- Maps standard statuses to visual states.
- Clicking an agent opens the same session detail panel used by the console.

Office/Building is a projection of the same backend state, not a separate backend model.

## Data Model

### Machine

Fields:

- `machine_id`
- `hostname`
- `labels`
- `collector_version`
- `last_heartbeat_at`
- `health`
- `runtime_inventory`

### RuntimeSession

Fields:

- `runtime_type`: `codex`, `claude_code`, `hermes`
- `session_id`
- `machine_id`
- `cwd`
- `project_name`
- `model`
- `status`
- `current_task`
- `progress_summary`
- `last_event_at`
- `capabilities`
- `source_ref`

### AgentInstance

Fields:

- `agent_id`
- `session_id`
- `parent_agent_id`
- `native_agent_id`
- `agent_type`
- `status`
- `task_description`
- `progress_summary`
- `capabilities`

### EventRecord

Append-only event log.

Fields:

- `event_id`
- `machine_id`
- `runtime_type`
- `session_id`
- `agent_id`
- `event_type`
- `timestamp`
- `payload`
- `source_ref`

### ControlCommand

Fields:

- `command_id`
- `target_machine_id`
- `target_session_id`
- `target_agent_id`
- `action`
- `payload`
- `actor`
- `status`: `queued`, `leased`, `applied`, `failed`, `expired`
- `created_at`
- `leased_at`
- `completed_at`
- `result_summary`
- `audit_metadata`

### Standard Statuses

UI consumes normalized statuses:

- `starting`
- `idle`
- `working`
- `waiting_input`
- `waiting_permission`
- `blocked`
- `completed`
- `lost`

Native runtime statuses can remain in raw payloads, but projector output uses the standard status set.

## Event Flow

1. Runtime emits native signal through hook, log, API, or probe.
2. Collector adapter normalizes the signal.
3. Collector assigns deterministic event identity where possible.
4. Collector sends event batch to central.
5. Central authenticates, validates, deduplicates, and persists events.
6. Projector updates current machine/session/agent state.
7. WebSocket notifies connected UI clients.

Deduplication should use `event_id` where available; otherwise source cursor plus runtime/session/timestamp/tool identifiers.

## Control Flow

1. User opens a session/agent in the UI.
2. UI shows only actions present in the target `capabilities`.
3. User submits action payload.
4. Central creates `ControlCommand` with status `queued` and audit metadata.
5. Matching collector polls and leases the command.
6. Collector executes through the runtime adapter.
7. Collector posts result.
8. Central persists command result and emits a result event.
9. Projector updates command/session state.

Supported MVP actions:

- `append_prompt`: add an instruction to a target session through the adapter-supported transport.
- `request_report`: ask the agent to summarize current progress, blockers, and next step.
- `continue`: ask the agent to continue its current task.

## Error Handling

- Collector offline: central marks machine/session as `lost` after heartbeat timeout.
- Network failure: collector buffers events locally and retries with backoff.
- Unsupported action: blocked by capability gating before command creation.
- Command not leased: expires after TTL.
- Command leased but no result: returns to queued or expires based on lease TTL policy.
- Adapter execution failure: command becomes `failed` with adapter error summary.
- Duplicate events: ignored or idempotently re-applied.
- Invalid payload: central rejects and logs validation error.

## Testing Strategy

Backend:

- Projector unit tests for deterministic state from event sequences.
- Command queue tests for create, lease, TTL, result, expiration, and failure.
- API validation tests for event ingestion and command creation.
- Deduplication tests for repeated events.

Collector:

- Fake adapter tests for event normalization.
- Buffer/retry tests.
- Capability declaration tests.
- Command execution/result tests.

Frontend:

- Smoke tests for session table, session detail, action drawer, and WebSocket updates.
- Capability gating tests to ensure unsupported actions are hidden.
- Office projection smoke test using fixed projected state.

Integration:

- End-to-end fake collector flow: heartbeat, event batch, projected session, command lease, command result.
- At least one real local Codex or Claude hook smoke path once implementation reaches adapter wiring.

## MVP Implementation Order

1. Scaffold repo and app skeleton.
2. Define shared schemas and event/status/action enums.
3. Implement central storage, ingestion API, command queue, and projector.
4. Implement fake collector and fake adapter for integration testing.
5. Implement WebSocket and minimal console UI.
6. Add Codex adapter.
7. Add Claude Code adapter.
8. Add Hermes adapter.
9. Add Office/Building projection view.
10. Harden audit, docs, and deployment instructions.

## Open Decisions

- Exact persistence backend: start with SQLite while keeping schema Postgres-friendly.
- Exact Codex/Claude prompt-injection transport for `append_prompt`; must be adapter-specific and capability gated.
- How much Hermes control is available depends on current Hermes APIs.
- Whether collectors run as user services, tmux sessions, or supervised processes.
