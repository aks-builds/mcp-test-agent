import json
import threading
import time

import httpx
import pytest
import uvicorn
from playwright.sync_api import sync_playwright

from demo_app.main import app as demo_app, reset_tasks
import servers.ticket_spec.server as ticket_spec_server
import servers.api_test.server as api_test_server
from servers.reporting import server as reporting_server

DEMO_APP_PORT = 8000
DEMO_APP_URL = f"http://127.0.0.1:{DEMO_APP_PORT}"


@pytest.fixture(scope="module")
def running_demo_app():
    reset_tasks()
    config = uvicorn.Config(demo_app, host="127.0.0.1", port=DEMO_APP_PORT, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 5
    started = False
    while time.time() < deadline:
        try:
            httpx.get(f"{DEMO_APP_URL}/openapi.json", timeout=0.5)
            started = True
            break
        except httpx.TransportError:
            time.sleep(0.1)
    if not started:
        pytest.fail("demo app did not start in time")
    yield
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(autouse=True)
def use_tmp_reporting_files(tmp_path, monkeypatch):
    jira_file = tmp_path / "jira_comments.json"
    slack_file = tmp_path / "slack_messages.json"
    monkeypatch.setattr(reporting_server, "JIRA_FILE", jira_file)
    monkeypatch.setattr(reporting_server, "SLACK_FILE", slack_file)
    return jira_file, slack_file


def test_full_demo_path_end_to_end(running_demo_app, use_tmp_reporting_files, monkeypatch):
    monkeypatch.setattr(ticket_spec_server, "DEMO_APP_URL", DEMO_APP_URL)
    monkeypatch.setattr(api_test_server, "DEMO_APP_URL", DEMO_APP_URL)

    # 1. Ticket/Spec MCP
    ticket = ticket_spec_server.get_ticket("NASH-101")
    assert "Given" in ticket["description"]

    spec = ticket_spec_server.get_openapi_spec()
    assert "/tasks" in spec["paths"]

    # 2. UI execution, hit the planted stale locator, then self-heal
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(DEMO_APP_URL)
        page.fill("#task-title", "Buy milk")

        assert page.locator("#add-task-btn").count() == 0  # the drift is real

        healed_button = page.get_by_role("button", name="Add Task")
        healed_button.click()

        page.wait_for_selector("#task-list li:has-text('Buy milk')")
        browser.close()

    # 3. API-level checks
    result = api_test_server.run_api_test("GET", "/tasks", expected_status=200)
    assert result["passed"] is True
    assert any(t["title"] == "Buy milk" for t in result["response_body"])

    # 4. Reporting
    jira_result = reporting_server.post_jira_comment(
        "NASH-101",
        "UI test passed after self-healing #add-task-btn to role=button "
        "name='Add Task'. API test passed.",
    )
    assert jira_result["posted"] is True

    slack_result = reporting_server.post_slack_message(
        "#qa-alerts", "NASH-101: all tests passed (1 self-heal)."
    )
    assert slack_result["posted"] is True

    jira_file, _ = use_tmp_reporting_files
    jira_store = json.loads(jira_file.read_text(encoding="utf-8"))
    assert "self-healing" in jira_store["NASH-101"][0]["comment"]
