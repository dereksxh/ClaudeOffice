from pathlib import Path


def test_readme_documents_server_collector_and_token() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "AGENT_OFFICE_TOKEN=dev-token agent-office-server --host 0.0.0.0 --port 8080" in readme
    assert "AGENT_OFFICE_TOKEN=dev-token agent-office-collector --central-url http://127.0.0.1:8080" in readme
    assert "append_prompt" in readme
    assert "request_report" in readme
    assert "continue" in readme
