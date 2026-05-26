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
AGENT_OFFICE_TOKEN=dev-token agent-office-server --host 0.0.0.0 --port 8080
```

Open:

```text
http://localhost:8080
```

## Run the collector against local central

```bash
AGENT_OFFICE_TOKEN=dev-token agent-office-collector --central-url http://127.0.0.1:8080
```

The first collector implementation includes a fake adapter for end-to-end smoke testing. Codex, Claude Code, and Hermes adapters normalize runtime-specific signals into the same event schema.

## Security model

The MVP is for trusted internal use. Every API request uses the shared `AGENT_OFFICE_TOKEN`. Every control action is persisted as a command record with actor, target, payload summary, status, timestamps, and result.

High-risk controls such as kill, restart, and pause are outside the MVP.
