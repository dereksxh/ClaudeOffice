from pathlib import Path


WEB_DIR = Path("src/agent_office/web")


def test_web_app_contains_console_regions() -> None:
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")

    assert 'id="machine-list"' in html
    assert 'id="console-screen"' in html
    assert 'id="session-table"' in html
    assert 'id="session-detail"' in html
    assert 'data-view-target="office"' in html
    assert 'id="office-screen"' in html
    assert 'id="office-view"' in html
    assert 'id="token-usage-summary"' in html


def test_web_app_gates_actions_by_capability() -> None:
    js = (WEB_DIR / "app.js").read_text(encoding="utf-8")

    assert "renderActions" in js
    assert "append_prompt" in js
    assert "request_report" in js
    assert "continue" in js
    assert "session.capabilities.includes(action)" in js


def test_web_app_collects_append_prompt_text() -> None:
    js = (WEB_DIR / "app.js").read_text(encoding="utf-8")

    assert 'window.prompt("Prompt to append")' in js


def test_web_app_reconnects_websocket_on_close() -> None:
    js = (WEB_DIR / "app.js").read_text(encoding="utf-8")

    assert "setTimeout(connectWebSocket" in js


def test_web_app_filters_detail_commands_by_session_and_machine() -> None:
    js = (WEB_DIR / "app.js").read_text(encoding="utf-8")

    assert "command.target_session_id === session.session_id" in js
    assert "command.target_machine_id === session.machine_id" in js
    assert "agent.session_id === session.session_id" in js
    assert "agent.machine_id === session.machine_id" in js


def test_web_app_does_not_embed_default_control_token() -> None:
    js = (WEB_DIR / "app.js").read_text(encoding="utf-8")

    assert "dev-token" not in js


def test_web_app_switches_between_console_and_office_views() -> None:
    js = (WEB_DIR / "app.js").read_text(encoding="utf-8")

    assert "setActiveView" in js
    assert "[data-view-target]" in js
    assert ".view-screen" in js


def test_web_app_keeps_office_nodes_stable_between_state_updates() -> None:
    js = (WEB_DIR / "app.js").read_text(encoding="utf-8")

    assert "officeDeskNodes" in js
    assert "removeStaleOfficeNodes" in js
    assert "officeView.replaceChildren();" not in js


def test_web_app_groups_office_by_runtime_and_assigns_mascots() -> None:
    js = (WEB_DIR / "app.js").read_text(encoding="utf-8")

    assert "sessionsByRuntime" in js
    assert "ensureOfficeRuntimeNode" in js
    assert "runtimeTypeLabel" in js
    assert "mascotForRuntime" in js
    assert "mascot-cow" in js
    assert "mascot-pony" in js


def test_web_app_assigns_stable_idle_activities() -> None:
    js = (WEB_DIR / "app.js").read_text(encoding="utf-8")

    assert "idleActivityForSession" in js
    assert '"sleeping"' in js
    assert '"phone"' in js
    assert '"chatting"' in js
    assert "activity-${activity}" in js


def test_web_app_normalizes_status_underscores_for_css_classes() -> None:
    js = (WEB_DIR / "app.js").read_text(encoding="utf-8")

    assert '.replaceAll("_", "-")' in js


def test_web_app_renders_token_usage_summary() -> None:
    js = (WEB_DIR / "app.js").read_text(encoding="utf-8")

    assert "token_usage: nextState.token_usage || []" in js
    assert "renderTokenUsage" in js
    assert "formatCompactNumber" in js
    assert "tokenUsageSummary" in js


def test_web_styles_keep_dense_console_layout() -> None:
    css = (WEB_DIR / "styles.css").read_text(encoding="utf-8")

    assert ".app-shell" in css
    assert ".session-table" in css
    assert ".office-grid" in css
    assert ".usage-panel" in css


def test_web_styles_include_animated_office_projection() -> None:
    css = (WEB_DIR / "styles.css").read_text(encoding="utf-8")

    assert ".office-floor" in css
    assert ".office-desk" in css
    assert ".office-runtime-zone" in css
    assert ".desk-surface" in css
    assert ".mascot-cow" in css
    assert ".mascot-pony" in css
    assert ".agent-person.working" in css
    assert ".agent-person.activity-sleeping" in css
    assert ".agent-person.activity-phone" in css
    assert ".agent-person.activity-chatting" in css
    assert ".agent-person.waiting-permission" in css
    assert "@keyframes deskPulse" in css
    assert "@keyframes typingDot" in css
    assert "@keyframes sleepingBreath" in css
    assert "@keyframes phoneTap" in css
