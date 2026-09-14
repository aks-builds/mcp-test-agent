# MCP Test Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the demoable MCP Test Agent prototype for the NashLearn "Building Test Agents with MCP Servers" session (23 Oct 2026) — one agent orchestrating four MCP servers to read a ticket + OpenAPI spec, plan a test strategy, execute UI and API tests, self-heal a drifted locator, and report results to a mock Jira/Slack.

**Architecture:** A small FastAPI "Task Tracker" demo app is the system under test. Three purpose-built Python MCP servers (Ticket/Spec, API-Test, Reporting) plus the official Playwright MCP server expose narrow tool sets to an orchestrating agent. A tiny FastAPI dashboard renders the mock Jira/Slack feeds live. Everything runs locally over stdio/localhost — no remote hosting, no real third-party accounts.

**Tech Stack:** Python 3.11+, FastAPI + uvicorn, official `mcp` Python SDK (FastMCP), httpx, pytest + respx for mocking, Playwright (Python, for the integration test) + Playwright MCP (Node, official, for the live demo only).

**Spec:** `C:\NashTech\mcp-test-agent\docs\superpowers\specs\2026-09-14-mcp-test-agent-design.md`

## Global Constraints

- No real Jira/Slack accounts — all reporting targets are local mock stores.
- No remote/streamable-HTTP hosting of any of the four servers — stdio/local only.
- Adaptation on failure is self-healing only (locator drift) — no root-cause re-diagnosis/re-planning behavior is implemented.
- The ticket's Given/When/Then structure is optional, never required/enforced by the Ticket/Spec MCP.
- Reporting MCP writes go through immediately — no `dry_run` gate (targets are already local mocks, no real external side effect to protect).
- Each of the four MCP servers must be independently startable and testable — no server may import from or depend on another server's internals, only on the shared demo app (via HTTP) and its own local data store.

---

### Task 1: Demo app — Task Tracker API + UI

**Files:**
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `demo_app/__init__.py`
- Create: `demo_app/main.py`
- Create: `demo_app/static/index.html`
- Test: `tests/unit/test_demo_app.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `demo_app.main.app` (FastAPI instance), `demo_app.main.reset_tasks() -> None`. Endpoints: `GET /tasks -> list[Task]`, `POST /tasks {title: str} -> Task (201)`, `POST /tasks/{id}/complete -> Task (200) | 404`, where `Task = {id: int, title: str, completed: bool}`. Static UI at `GET /` with: text input `#task-title`, button `id="save-task-btn"` (accessible role `button`, name `"Add Task"`), list `#task-list`.

- [ ] **Step 1: Scaffolding — pyproject.toml, requirements.txt, package init**

`pyproject.toml`:
```toml
[tool.pytest.ini_options]
pythonpath = ["."]
```

`requirements.txt`:
```
fastapi
uvicorn[standard]
httpx
pytest
```

`demo_app/__init__.py`: empty file.

- [ ] **Step 2: Write the failing test for create + list**

`tests/unit/test_demo_app.py`:
```python
from fastapi.testclient import TestClient

from demo_app.main import app, reset_tasks

client = TestClient(app)


def setup_function():
    reset_tasks()


def test_create_and_list_task():
    resp = client.post("/tasks", json={"title": "Buy milk"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Buy milk"
    assert body["completed"] is False

    resp = client.get("/tasks")
    assert resp.status_code == 200
    tasks = resp.json()
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Buy milk"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/unit/test_demo_app.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'demo_app.main'`

- [ ] **Step 4: Implement minimal demo_app/main.py (create + list only)**

`demo_app/main.py`:
```python
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="Task Tracker", version="1.0.0")

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

_tasks: list[dict] = []
_next_id = 1


class TaskCreate(BaseModel):
    title: str


class Task(BaseModel):
    id: int
    title: str
    completed: bool


def reset_tasks() -> None:
    global _tasks, _next_id
    _tasks = []
    _next_id = 1


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/tasks", response_model=list[Task])
def list_tasks():
    return _tasks


@app.post("/tasks", response_model=Task, status_code=201)
def create_task(payload: TaskCreate):
    global _next_id
    task = {"id": _next_id, "title": payload.title, "completed": False}
    _tasks.append(task)
    _next_id += 1
    return task
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/test_demo_app.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml requirements.txt demo_app/__init__.py demo_app/main.py tests/unit/test_demo_app.py
git commit -m "feat: task tracker create + list endpoints"
```

- [ ] **Step 7: Write the failing test for complete + 404**

Append to `tests/unit/test_demo_app.py`:
```python
def test_complete_task():
    created = client.post("/tasks", json={"title": "Buy milk"}).json()
    resp = client.post(f"/tasks/{created['id']}/complete")
    assert resp.status_code == 200
    assert resp.json()["completed"] is True


def test_complete_missing_task_404():
    resp = client.post("/tasks/999/complete")
    assert resp.status_code == 404
```

- [ ] **Step 8: Run test to verify it fails**

Run: `pytest tests/unit/test_demo_app.py -v`
Expected: FAIL — `test_complete_task` and `test_complete_missing_task_404` fail with 404 "Not Found" (route doesn't exist yet).

- [ ] **Step 9: Implement complete endpoint**

Append to `demo_app/main.py`:
```python
@app.post("/tasks/{task_id}/complete", response_model=Task)
def complete_task(task_id: int):
    for task in _tasks:
        if task["id"] == task_id:
            task["completed"] = True
            return task
    raise HTTPException(status_code=404, detail="Task not found")
```

- [ ] **Step 10: Run test to verify it passes**

Run: `pytest tests/unit/test_demo_app.py -v`
Expected: PASS (all 3 tests)

- [ ] **Step 11: Commit**

```bash
git add demo_app/main.py tests/unit/test_demo_app.py
git commit -m "feat: task tracker complete endpoint"
```

- [ ] **Step 12: Add the static UI (no automated unit test — verified by the Task 6 integration test)**

`demo_app/static/index.html`:
```html
<!DOCTYPE html>
<html>
<head><title>Task Tracker</title></head>
<body>
  <h1>Task Tracker</h1>
  <input id="task-title" type="text" placeholder="New task title" />
  <button id="save-task-btn">Add Task</button>
  <ul id="task-list"></ul>
  <script>
    async function loadTasks() {
      const res = await fetch('/tasks');
      const tasks = await res.json();
      const list = document.getElementById('task-list');
      list.innerHTML = '';
      for (const t of tasks) {
        const li = document.createElement('li');
        li.textContent = t.title + (t.completed ? ' (done)' : '');
        list.appendChild(li);
      }
    }
    document.getElementById('save-task-btn').addEventListener('click', async () => {
      const input = document.getElementById('task-title');
      if (!input.value) return;
      await fetch('/tasks', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({title: input.value})
      });
      input.value = '';
      loadTasks();
    });
    loadTasks();
  </script>
</body>
</html>
```

Note the real button id is `save-task-btn` — this is the planted drift target. The ticket (Task 2) will reference the older `#add-task-btn` id, which no longer exists.

- [ ] **Step 13: Commit**

```bash
git add demo_app/static/index.html
git commit -m "feat: task tracker UI with planted locator drift (save-task-btn)"
```

---

### Task 2: Ticket/Spec MCP server

**Files:**
- Create: `data/tickets.json`
- Create: `servers/__init__.py`
- Create: `servers/ticket_spec/__init__.py`
- Create: `servers/ticket_spec/server.py`
- Test: `tests/unit/test_ticket_spec_server.py`
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: demo app's `GET /openapi.json` over HTTP at `DEMO_APP_URL` (default `http://127.0.0.1:8000`) — mocked in unit tests via `respx`, real in the Task 6 integration test.
- Produces: `servers.ticket_spec.server.get_ticket(ticket_id: str) -> dict`, `servers.ticket_spec.server.get_openapi_spec() -> dict`, module-level `DEMO_APP_URL: str`, `DATA_FILE: Path`.

- [ ] **Step 1: Add the mock ticket data**

`data/tickets.json`:
```json
{
  "NASH-101": {
    "id": "NASH-101",
    "title": "Add Task creation flow should work end-to-end",
    "description": "As a user, I want to add a new task so I can track my work.\n\nGiven the task tracker is loaded\nWhen I enter a task title and click \"Add Task\"\nThen the task appears in the task list\n\nAcceptance criteria:\n- POST /tasks creates a task and returns 201\n- The new task appears in GET /tasks\n- The UI \"Add Task\" button adds the task to the visible list\n\nAutomation notes: earlier smoke-test automation targeted the button by id #add-task-btn. Confirm this still locates the button before relying on it."
  }
}
```

- [ ] **Step 2: Add mcp + respx to requirements.txt**

Append to `requirements.txt`:
```
mcp
respx
```

- [ ] **Step 3: Write the failing tests**

`servers/__init__.py`: empty file.
`servers/ticket_spec/__init__.py`: empty file.

`tests/unit/test_ticket_spec_server.py`:
```python
import httpx
import respx

from servers.ticket_spec.server import get_ticket, get_openapi_spec


def test_get_ticket_returns_known_ticket():
    result = get_ticket("NASH-101")
    assert result["id"] == "NASH-101"
    assert "Given" in result["description"]
    assert "#add-task-btn" in result["description"]


def test_get_ticket_unknown_id_returns_error():
    result = get_ticket("NASH-999")
    assert result == {"error": "ticket NASH-999 not found"}


@respx.mock
def test_get_openapi_spec_fetches_from_demo_app():
    respx.get("http://127.0.0.1:8000/openapi.json").mock(
        return_value=httpx.Response(200, json={"openapi": "3.1.0", "paths": {}})
    )
    result = get_openapi_spec()
    assert result["openapi"] == "3.1.0"
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/unit/test_ticket_spec_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'servers.ticket_spec.server'`

- [ ] **Step 5: Implement the server**

`servers/ticket_spec/server.py`:
```python
import json
import os
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "tickets.json"
DEMO_APP_URL = os.environ.get("DEMO_APP_URL", "http://127.0.0.1:8000")

mcp = FastMCP("ticket-spec")


def _load_tickets() -> dict:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


@mcp.tool()
def get_ticket(ticket_id: str) -> dict:
    """Fetch a mock Jira ticket by id. Returns its title and description
    (description may contain an optional Given/When/Then block)."""
    tickets = _load_tickets()
    if ticket_id not in tickets:
        return {"error": f"ticket {ticket_id} not found"}
    return tickets[ticket_id]


@mcp.tool()
def get_openapi_spec() -> dict:
    """Fetch the target demo app's live OpenAPI spec."""
    resp = httpx.get(f"{DEMO_APP_URL}/openapi.json", timeout=5.0)
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    mcp.run()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/unit/test_ticket_spec_server.py -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Commit**

```bash
git add data/tickets.json servers/__init__.py servers/ticket_spec/ tests/unit/test_ticket_spec_server.py requirements.txt
git commit -m "feat: ticket/spec MCP server"
```

---

### Task 3: API-Test MCP server

**Files:**
- Create: `servers/api_test/__init__.py`
- Create: `servers/api_test/server.py`
- Test: `tests/unit/test_api_test_server.py`

**Interfaces:**
- Consumes: demo app's HTTP endpoints at `DEMO_APP_URL` (Task 1) — mocked via `respx` in unit tests.
- Produces: `servers.api_test.server.run_api_test(method: str, path: str, body: dict | None = None, expected_status: int = 200) -> dict` returning `{passed: bool, method: str, path: str, expected_status: int, actual_status: int, response_body: Any}`. Module-level `DEMO_APP_URL: str`.

- [ ] **Step 1: Write the failing tests**

`servers/api_test/__init__.py`: empty file.

`tests/unit/test_api_test_server.py`:
```python
import httpx
import respx

from servers.api_test.server import run_api_test


@respx.mock
def test_run_api_test_passes_on_matching_status():
    respx.post("http://127.0.0.1:8000/tasks").mock(
        return_value=httpx.Response(201, json={"id": 1, "title": "Buy milk", "completed": False})
    )
    result = run_api_test("POST", "/tasks", body={"title": "Buy milk"}, expected_status=201)
    assert result["passed"] is True
    assert result["actual_status"] == 201
    assert result["response_body"]["title"] == "Buy milk"


@respx.mock
def test_run_api_test_fails_on_mismatched_status():
    respx.post("http://127.0.0.1:8000/tasks/999/complete").mock(
        return_value=httpx.Response(404, json={"detail": "Task not found"})
    )
    result = run_api_test("POST", "/tasks/999/complete", expected_status=200)
    assert result["passed"] is False
    assert result["actual_status"] == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_api_test_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'servers.api_test.server'`

- [ ] **Step 3: Implement the server**

`servers/api_test/server.py`:
```python
import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

DEMO_APP_URL = os.environ.get("DEMO_APP_URL", "http://127.0.0.1:8000")

mcp = FastMCP("api-test")


@mcp.tool()
def run_api_test(
    method: str,
    path: str,
    body: dict | None = None,
    expected_status: int = 200,
) -> dict:
    """Execute an HTTP call against the demo app and assert the response
    status matches expected_status. Returns a structured pass/fail result —
    never raises for a failed assertion, only for a transport-level error."""
    url = f"{DEMO_APP_URL}{path}"
    response = httpx.request(method.upper(), url, json=body, timeout=5.0)
    passed = response.status_code == expected_status
    return {
        "passed": passed,
        "method": method.upper(),
        "path": path,
        "expected_status": expected_status,
        "actual_status": response.status_code,
        "response_body": _safe_json(response),
    }


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


if __name__ == "__main__":
    mcp.run()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_api_test_server.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add servers/api_test/ tests/unit/test_api_test_server.py
git commit -m "feat: api-test MCP server"
```

---

### Task 4: Reporting MCP server + local dashboard

**Files:**
- Create: `.gitignore`
- Create: `servers/reporting/__init__.py`
- Create: `servers/reporting/server.py`
- Create: `servers/reporting/dashboard.py`
- Create: `servers/reporting/static/dashboard.html`
- Test: `tests/unit/test_reporting_server.py`
- Test: `tests/unit/test_reporting_dashboard.py`

**Interfaces:**
- Consumes: nothing from other servers — independent local JSON stores.
- Produces: `servers.reporting.server.post_jira_comment(ticket_id: str, comment: str) -> dict` (`{"posted": True, "ticket_id": ...}`), `servers.reporting.server.post_slack_message(channel: str, text: str) -> dict` (`{"posted": True, "channel": ...}`), module-level `JIRA_FILE: Path`, `SLACK_FILE: Path`. `servers.reporting.dashboard.app` (FastAPI) with `GET /api/jira -> dict`, `GET /api/slack -> dict`, module-level `JIRA_FILE: Path`, `SLACK_FILE: Path`.

- [ ] **Step 1: Add .gitignore for the mutable data stores**

`.gitignore`:
```
data/jira_comments.json
data/slack_messages.json
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 2: Write the failing tests for the reporting server**

`servers/reporting/__init__.py`: empty file.

`tests/unit/test_reporting_server.py`:
```python
import json

import pytest

from servers.reporting import server as reporting_server


@pytest.fixture(autouse=True)
def use_tmp_data_files(tmp_path, monkeypatch):
    jira_file = tmp_path / "jira_comments.json"
    slack_file = tmp_path / "slack_messages.json"
    monkeypatch.setattr(reporting_server, "JIRA_FILE", jira_file)
    monkeypatch.setattr(reporting_server, "SLACK_FILE", slack_file)
    return jira_file, slack_file


def test_post_jira_comment_appends_to_store(use_tmp_data_files):
    jira_file, _ = use_tmp_data_files
    result = reporting_server.post_jira_comment("NASH-101", "All tests passed.")
    assert result == {"posted": True, "ticket_id": "NASH-101"}
    store = json.loads(jira_file.read_text(encoding="utf-8"))
    assert store["NASH-101"][0]["comment"] == "All tests passed."


def test_post_slack_message_appends_to_store(use_tmp_data_files):
    _, slack_file = use_tmp_data_files
    result = reporting_server.post_slack_message("#qa-alerts", "Build green.")
    assert result == {"posted": True, "channel": "#qa-alerts"}
    store = json.loads(slack_file.read_text(encoding="utf-8"))
    assert store["#qa-alerts"][0]["text"] == "Build green."


def test_post_jira_comment_appends_multiple_entries(use_tmp_data_files):
    jira_file, _ = use_tmp_data_files
    reporting_server.post_jira_comment("NASH-101", "First.")
    reporting_server.post_jira_comment("NASH-101", "Second.")
    store = json.loads(jira_file.read_text(encoding="utf-8"))
    assert [e["comment"] for e in store["NASH-101"]] == ["First.", "Second."]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/unit/test_reporting_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'servers.reporting.server'`

- [ ] **Step 4: Implement the reporting server**

`servers/reporting/server.py`:
```python
import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
JIRA_FILE = DATA_DIR / "jira_comments.json"
SLACK_FILE = DATA_DIR / "slack_messages.json"

mcp = FastMCP("reporting")


def _append(path: Path, key: str, entry: dict) -> None:
    store = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    store.setdefault(key, []).append(entry)
    path.write_text(json.dumps(store, indent=2), encoding="utf-8")


@mcp.tool()
def post_jira_comment(ticket_id: str, comment: str) -> dict:
    """Post a comment to the mock Jira ticket thread."""
    _append(JIRA_FILE, ticket_id, {"comment": comment})
    return {"posted": True, "ticket_id": ticket_id}


@mcp.tool()
def post_slack_message(channel: str, text: str) -> dict:
    """Post a message to the mock Slack channel feed."""
    _append(SLACK_FILE, channel, {"text": text})
    return {"posted": True, "channel": channel}


if __name__ == "__main__":
    mcp.run()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_reporting_server.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add .gitignore servers/reporting/__init__.py servers/reporting/server.py tests/unit/test_reporting_server.py
git commit -m "feat: reporting MCP server"
```

- [ ] **Step 7: Write the failing tests for the dashboard**

`tests/unit/test_reporting_dashboard.py`:
```python
import json

import pytest
from fastapi.testclient import TestClient

from servers.reporting import dashboard


@pytest.fixture
def client(tmp_path, monkeypatch):
    jira_file = tmp_path / "jira_comments.json"
    slack_file = tmp_path / "slack_messages.json"
    jira_file.write_text(json.dumps({"NASH-101": [{"comment": "hi"}]}), encoding="utf-8")
    slack_file.write_text(json.dumps({"#qa-alerts": [{"text": "hello"}]}), encoding="utf-8")
    monkeypatch.setattr(dashboard, "JIRA_FILE", jira_file)
    monkeypatch.setattr(dashboard, "SLACK_FILE", slack_file)
    return TestClient(dashboard.app)


def test_jira_feed_returns_stored_comments(client):
    resp = client.get("/api/jira")
    assert resp.status_code == 200
    assert resp.json()["NASH-101"][0]["comment"] == "hi"


def test_slack_feed_returns_stored_messages(client):
    resp = client.get("/api/slack")
    assert resp.status_code == 200
    assert resp.json()["#qa-alerts"][0]["text"] == "hello"


def test_jira_feed_empty_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard, "JIRA_FILE", tmp_path / "missing.json")
    monkeypatch.setattr(dashboard, "SLACK_FILE", tmp_path / "missing2.json")
    client = TestClient(dashboard.app)
    assert client.get("/api/jira").json() == {}
```

- [ ] **Step 8: Run tests to verify they fail**

Run: `pytest tests/unit/test_reporting_dashboard.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'servers.reporting.dashboard'`

- [ ] **Step 9: Implement the dashboard**

`servers/reporting/dashboard.py`:
```python
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
JIRA_FILE = DATA_DIR / "jira_comments.json"
SLACK_FILE = DATA_DIR / "slack_messages.json"
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Reporting Dashboard")


def _read(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "dashboard.html")


@app.get("/api/jira")
def jira_feed():
    return _read(JIRA_FILE)


@app.get("/api/slack")
def slack_feed():
    return _read(SLACK_FILE)
```

`servers/reporting/static/dashboard.html`:
```html
<!DOCTYPE html>
<html>
<head><title>Mock Jira + Slack Dashboard</title></head>
<body>
  <h1>Live Reporting Feed</h1>
  <div style="display:flex; gap:2rem;">
    <section>
      <h2>Jira</h2>
      <pre id="jira"></pre>
    </section>
    <section>
      <h2>Slack</h2>
      <pre id="slack"></pre>
    </section>
  </div>
  <script>
    async function refresh() {
      const jira = await (await fetch('/api/jira')).json();
      const slack = await (await fetch('/api/slack')).json();
      document.getElementById('jira').textContent = JSON.stringify(jira, null, 2);
      document.getElementById('slack').textContent = JSON.stringify(slack, null, 2);
    }
    refresh();
    setInterval(refresh, 1500);
  </script>
</body>
</html>
```

- [ ] **Step 10: Run tests to verify they pass**

Run: `pytest tests/unit/test_reporting_dashboard.py -v`
Expected: PASS (3 tests)

- [ ] **Step 11: Commit**

```bash
git add servers/reporting/dashboard.py servers/reporting/static/dashboard.html tests/unit/test_reporting_dashboard.py
git commit -m "feat: reporting dashboard"
```

---

### Task 5: Agent runbook

**Files:**
- Create: `AGENT_RUNBOOK.md`

**Interfaces:**
- Consumes: Tasks 1-4 (documents how to start and orchestrate them).
- Produces: `AGENT_RUNBOOK.md` — the instructions the live orchestrating agent follows during the demo.

- [ ] **Step 1: Write the runbook**

`AGENT_RUNBOOK.md`:
```markdown
# Agent Runbook — MCP Test Agent

You are orchestrating a self-directed test run. Four MCP servers are
available. Call their tools in this order.

## Servers

| Server | Start command | Purpose |
|---|---|---|
| ticket-spec | `python -m servers.ticket_spec.server` | `get_ticket`, `get_openapi_spec` |
| api-test | `python -m servers.api_test.server` | `run_api_test` |
| reporting | `python -m servers.reporting.server` | `post_jira_comment`, `post_slack_message` |
| Playwright MCP | `npx @playwright/mcp@latest` | browser automation (`navigate`, `snapshot`, `click`, `fill`, ...) |

The target app must be running first: `uvicorn demo_app.main:app --port 8000`.

## Procedure

1. Call `ticket-spec.get_ticket(ticket_id)` to read the ticket. If it
   contains a Given/When/Then block, use it directly as your test
   strategy. If it is plain prose, extract the user-facing behavior
   yourself before continuing.
2. Call `ticket-spec.get_openapi_spec()` to see the real API surface.
3. Draft a short test strategy: which UI flow(s) and which API
   endpoint(s) cover the ticket's acceptance criteria.
4. Execute the UI flow using Playwright MCP against `http://127.0.0.1:8000/`.
   The ticket may reference a locator used by earlier automation (e.g. a
   button id) — try that first.
   - If a `click`/`fill` action fails because the target locator is not
     found:
     a. Call Playwright MCP's `snapshot` tool to get the current
        accessibility tree.
     b. Find the element with the same role and accessible name that the
        ticket implied (e.g. a button named "Add Task").
     c. Retry the action using that element instead.
     d. State explicitly what locator you replaced and why, citing the
        snapshot — never silently substitute a locator without saying so.
5. Execute the API-level checks with `api-test.run_api_test(method, path,
   body, expected_status)` for each endpoint identified in step 3.
6. Summarize the run: what passed, what failed, what was self-healed and
   why.
7. Call `reporting.post_jira_comment(ticket_id, comment)` with the summary
   from step 6.
8. Call `reporting.post_slack_message(channel, text)` with a short version
   of the same summary. Use channel `#qa-alerts` unless told otherwise.

## Rules

- Never claim a test passed without having actually called the
  corresponding tool and observed a passing result.
- Every self-heal must name the old locator, the new locator, and the
  evidence (the snapshot) that justified the change.
- If a step fails and cannot be self-healed, report it as a failure in
  the summary — do not paper over it.
```

- [ ] **Step 2: Verify completeness**

Confirm the file covers all of: (a) all four servers with start commands, (b) the ordered 8-step procedure, (c) explicit self-heal sub-steps citing the snapshot as evidence, (d) the "never claim a pass without evidence" rule. All four present per Step 1's content above.

- [ ] **Step 3: Commit**

```bash
git add AGENT_RUNBOOK.md
git commit -m "docs: agent runbook for orchestrating the four MCP servers"
```

---

### Task 6: End-to-end integration test + README

**Files:**
- Create: `tests/integration/test_end_to_end_demo.py`
- Create: `README.md`
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: `demo_app.main.app`, `demo_app.main.reset_tasks` (Task 1); `servers.ticket_spec.server.get_ticket`, `.get_openapi_spec`, `.DEMO_APP_URL` (Task 2); `servers.api_test.server.run_api_test`, `.DEMO_APP_URL` (Task 3); `servers.reporting.server.post_jira_comment`, `.post_slack_message`, `.JIRA_FILE`, `.SLACK_FILE` (Task 4).
- Produces: `tests/integration/test_end_to_end_demo.py` (proves the full toolchain works deterministically without a live LLM agent), `README.md`.

- [ ] **Step 1: Add playwright + uvicorn to requirements.txt**

Append to `requirements.txt`:
```
playwright
```
(`uvicorn[standard]` is already present from Task 1.)

- [ ] **Step 2: Write the integration test**

`tests/integration/test_end_to_end_demo.py`:
```python
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

    # 2. UI execution — hit the planted stale locator, then self-heal
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
        "UI test passed after self-healing #add-task-btn -> role=button "
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
```

- [ ] **Step 3: Install the Playwright browser binary (one-time, not a test step)**

Run: `pip install -r requirements.txt && playwright install chromium`

- [ ] **Step 4: Run the integration test to verify it fails (before this is wired, expect import/collection errors only if any prior task is incomplete)**

Run: `pytest tests/integration/test_end_to_end_demo.py -v`
Expected: Since Tasks 1-4 already exist and pass their own unit tests by this point, this test should mostly work on first run modulo the reporting patch targets. If it fails, the failure must be a real assertion failure (e.g. selector mismatch), not an import error — fix forward until every assertion in Step 2 passes for the right reason.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/integration/test_end_to_end_demo.py -v`
Expected: PASS (1 test, exercising the full toolchain end-to-end)

- [ ] **Step 6: Write the README**

`README.md`:
```markdown
# MCP Test Agent

Demo tool for the NashLearn session "Building Test Agents with MCP Servers"
(23 Oct 2026). See
`docs/superpowers/specs/2026-09-14-mcp-test-agent-design.md` for the design
and `AGENT_RUNBOOK.md` for how an orchestrating agent should drive the four
MCP servers.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
```

## Run the demo app

```bash
uvicorn demo_app.main:app --port 8000
```

## Run the reporting dashboard

```bash
uvicorn servers.reporting.dashboard:app --port 8766
```

Open http://127.0.0.1:8766 to watch the mock Jira/Slack feed update live.

## Run the MCP servers

```bash
python -m servers.ticket_spec.server
python -m servers.api_test.server
python -m servers.reporting.server
npx @playwright/mcp@latest
```

Point an MCP-capable agent (e.g. Claude Code) at all four and follow
`AGENT_RUNBOOK.md`.

## Tests

```bash
pytest tests/unit
pytest tests/integration
```
```

- [ ] **Step 7: Run the full test suite one final time**

Run: `pytest tests/unit tests/integration -v`
Expected: PASS (all unit + integration tests)

- [ ] **Step 8: Commit**

```bash
git add tests/integration/test_end_to_end_demo.py README.md requirements.txt
git commit -m "test: end-to-end integration test + README"
```
