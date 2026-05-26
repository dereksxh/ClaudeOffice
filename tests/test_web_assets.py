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


def test_web_app_renders_idle_office_sessions_as_desks() -> None:
    js = (WEB_DIR / "app.js").read_text(encoding="utf-8")

    assert "visibleSessions" in js
    assert "officeTaskText" in js
    assert "ensureOfficeIdleNode" not in js
    assert "officeIdleNodes" not in js
    assert "office-idle-summary" not in js


def test_web_app_normalizes_status_underscores_for_css_classes() -> None:
    js = (WEB_DIR / "app.js").read_text(encoding="utf-8")

    assert '.replaceAll("_", "-")' in js


def test_web_app_uses_generated_office_sprite_assets() -> None:
    js = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    css = (WEB_DIR / "styles.css").read_text(encoding="utf-8")
    asset_dir = WEB_DIR / "assets" / "office"

    assert (asset_dir / "manifest.json").is_file()
    assert (asset_dir / "backgrounds" / "office.png").is_file()
    assert (asset_dir / "props" / "workstation-desk.png").is_file()
    for character in ("calf", "pony"):
        for activity in ("typing", "waiting", "idle-sleep", "idle-phone", "idle-chat", "stand"):
            assert (asset_dir / "characters" / character / f"{activity}-sheet-256.png").is_file()

    assert "officeSpriteCharacter" in js
    assert "officeSpriteActivity" in js
    assert "generated-agent" in js
    assert "generated-desk" in js
    assert "asset-idle-phone" in css
    assert "/assets/office/backgrounds/office.png" in css
    assert "/assets/office/props/workstation-desk.png" in css
    assert "calf/typing-sheet-256.png" in css
    assert "pony/typing-sheet-256.png" in css
    assert "@keyframes officeSpritePlay" in css


def test_web_app_renders_token_usage_summary() -> None:
    js = (WEB_DIR / "app.js").read_text(encoding="utf-8")

    assert "token_usage: nextState.token_usage || []" in js
    assert "renderTokenUsage" in js
    assert "formatCompactNumber" in js
    assert "tokenUsageSummary" in js
    assert "periods" in js
    assert "model_breakdown" in js
    assert "budget_used_ratio" in js
    assert "formatUsageCost" in js


def test_web_styles_keep_dense_console_layout() -> None:
    css = (WEB_DIR / "styles.css").read_text(encoding="utf-8")

    assert ".app-shell" in css
    assert ".session-table" in css
    assert ".office-grid" in css
    assert ".usage-panel" in css
    assert ".usage-periods" in css
    assert ".usage-models" in css


def test_web_styles_include_animated_office_projection() -> None:
    css = (WEB_DIR / "styles.css").read_text(encoding="utf-8")

    assert ".office-floor" in css
    assert ".office-desk" in css
    assert ".office-runtime-zone" in css
    assert ".office-stage-label" in css
    assert "border: 0;" in css
    assert "box-shadow: none;" in css
    assert ".mascot-cow" in css
    assert ".mascot-pony" in css
    assert ".generated-agent.asset-typing" in css
    assert ".generated-agent.asset-idle-sleep" in css
    assert ".generated-agent.asset-idle-phone" in css
    assert ".generated-agent.asset-idle-chat" in css
    assert ".generated-agent.asset-waiting" in css
    assert "@keyframes deskPulse" in css
    assert "@keyframes officeSpritePlay" in css
