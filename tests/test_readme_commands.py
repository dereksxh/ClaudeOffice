from pathlib import Path


def test_readme_documents_server_collector_and_token() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    assert 'export AGENT_OFFICE_TOKEN="$(openssl rand -hex 32)"' in readme
    assert "agent-office-server --host 127.0.0.1 --port 8080" in readme
    assert "agent-office-collector --central-url http://127.0.0.1:8080" in readme
    assert "--codex-sessions-dir ~/.codex/sessions" in readme
    assert "--hermes-home ~/.hermes" in readme
    assert "--codex-hook-log" in readme
    assert "--claude-hook-log" in readme
    assert "--hermes-snapshot" in readme
    assert "--command-outbox-dir" in readme
    assert "--enable-fake" in readme
    assert "dev-token" not in readme
    assert "append_prompt" in readme
    assert "request_report" in readme
    assert "continue" in readme
