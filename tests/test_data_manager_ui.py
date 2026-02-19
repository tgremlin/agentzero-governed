from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def test_data_manager_is_wired_as_full_screen_view() -> None:
    index_html = _read("webui/index.html")
    assert "css/data-manager.css" in index_html
    assert "x-component path=\"data-manager/data-manager-screen.html\"" in index_html
    assert "$store.dataManager && $store.dataManager.isOpen" in index_html


def test_data_events_buttons_open_data_manager_not_modal() -> None:
    quick_actions = _read("webui/components/sidebar/top-section/quick-actions.html")
    assert "$store.dataManager.open({ tab: 'governance', scope: 'global' })" in quick_actions
    assert "openModal('modals/data-events/data-events.html')" not in quick_actions


def test_chat_input_open_data_events_uses_scope_aware_data_manager() -> None:
    input_store = _read("webui/components/chat/input/input-store.js")
    assert "window.Alpine.store(\"dataManager\")" in input_store
    assert "dataManager.open({ tab: \"governance\", scope: hasContext ? \"chat\" : \"global\" })" in input_store


def test_data_manager_store_supports_scope_and_track_filters() -> None:
    store = _read("webui/components/data-manager/data-manager-store.js")
    assert "const ALLOWED_SCOPES = new Set([\"global\", \"project\", \"chat\"])" in store
    assert "candidate_track" in store
    assert "consent_scope" in store
    assert "return { context_id: contextId };" in store
    assert "return { project_name: projectName };" in store
    assert "trackCounts" in store


def test_snapshot_apply_does_not_fallback_to_other_chat_context() -> None:
    index_js = _read("webui/index.js")
    assert "setContext(firstChatId);" not in index_js
    assert "forcing a fallback leaks" in index_js
