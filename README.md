# Agent Office

Agent Office is an internal operations console for Codex CLI, Claude Code, and Hermes/self-hosted agents.

The MVP uses a central service plus lightweight machine collectors:

```text
runtime hooks/logs/probes -> collector -> central event store -> projector -> web UI
web UI -> command queue -> collector -> runtime adapter -> command result
```

## MVP capabilities

- central event ingestion and projected state
- machine collector with runtime adapters
- safe control commands: `append_prompt`, `request_report`, `continue`
- dense console UI and simple Office/Building projection
- shared token auth for trusted internal use

## Install for local development

```bash
python -m pip install -e '.[dev]'
```

## Run tests

```bash
python -m pytest
```

## Run central locally on port 8080

```bash
export AGENT_OFFICE_TOKEN="$(openssl rand -hex 32)"
agent-office-server --host 127.0.0.1 --port 8080
```

Open the page and enter the token when prompted:

```text
http://localhost:8080
```

## Run the collector against local central

For the current machine's Codex CLI sessions and Hermes gateways:

```bash
agent-office-collector --central-url http://127.0.0.1:8080 \
  --codex-sessions-dir ~/.codex/sessions \
  --hermes-home ~/.hermes
```

For hook/snapshot files exported by runtimes:

```bash
agent-office-collector --central-url http://127.0.0.1:8080 \
  --codex-hook-log ~/.agent-office/codex-hooks.jsonl \
  --claude-hook-log ~/.agent-office/claude-hooks.jsonl \
  --hermes-snapshot ~/.agent-office/hermes-snapshot.json \
  --command-outbox-dir ~/.agent-office/commands
```

Codex and Claude Code adapters read JSONL hook logs, Hermes reads a JSON snapshot file, and all configured runtimes write accepted control commands to runtime-specific JSONL outboxes. Runtime-specific signals are normalized into the same event schema.

For an end-to-end smoke test without real runtime files:

```bash
agent-office-collector --central-url http://127.0.0.1:8080 --enable-fake
```

## Security model

The MVP is for trusted internal use. Every API request uses the shared `AGENT_OFFICE_TOKEN`. Every control action is persisted as a command record with actor, target, payload summary, status, timestamps, and result.

High-risk controls such as kill, restart, and pause are outside the MVP.
