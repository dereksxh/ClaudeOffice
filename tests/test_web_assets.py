from pathlib import Path


WEB_DIR = Path("src/agent_office/web")


def test_web_app_contains_console_regions() -> None:
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")

    assert 'id="machine-list"' in html
    assert 'id="session-table"' in html
    assert 'id="session-detail"' in html
    assert 'id="office-view"' in html


def test_web_app_gates_actions_by_capability() -> None:
    js = (WEB_DIR / "app.js").read_text(encoding="utf-8")

    assert "renderActions" in js
    assert "append_prompt" in js
    assert "request_report" in js
    assert "continue" in js
    assert "session.capabilities.includes(action)" in js


def test_web_styles_keep_dense_console_layout() -> None:
    css = (WEB_DIR / "styles.css").read_text(encoding="utf-8")

    assert ".app-shell" in css
    assert ".session-table" in css
    assert ".office-grid" in css
