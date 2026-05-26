# Agent Office

Agent Office is an internal operations console for Codex CLI, Claude Code, and Hermes/self-hosted agents.

MVP capabilities:

- central event ingestion and projected state
- machine collector with runtime adapters
- safe control commands: append prompt, request report, continue
- dense console UI and simple Office/Building projection

Run tests:

```bash
python -m pytest
```

Run central locally:

```bash
AGENT_OFFICE_TOKEN=dev-token agent-office-server --host 0.0.0.0 --port 8080
```
