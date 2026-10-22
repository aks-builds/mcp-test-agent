"""test-mcp: one MCP server with several parts inside.

The agent (Claude Code, Gemini CLI, Codex CLI, OpenCode, or run.py)
connects to this one server. Each part is a small FastMCP of its own,
mounted here under a prefix, so the agent sees tools like
ticket_get_ticket, api_run_api_test, report_post_jira_comment and the
Playwright browser_* tools.

To add a part: write a module that exposes a FastMCP object called
`mcp`, then add one line to PARTS. Nothing else changes.

Every tool call passes through this server, so one middleware here
writes a trace line for every call to data/mcp_trace.jsonl. That is the
table run.py prints.
"""
import atexit
import importlib
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware

ROOT = Path(__file__).resolve().parents[2]
TRACE_FILE = Path(os.environ.get("MCP_TRACE_FILE", ROOT / "data" / "mcp_trace.jsonl"))

# (module that exposes `mcp`, prefix the umbrella adds to its tool names)
# Prefix None means the part's tool names are kept as they are.
PARTS = [
    ("servers.ticket_spec.server", "ticket"),
    ("servers.api_test.server", "api"),
    ("servers.reporting.server", "report"),
    ("servers.browser.server", None),  # Playwright already names its tools browser_*
]

INSTRUCTIONS_TEMPLATE = """You are a test agent. This server gives you everything you need to test
one Jira ticket end to end: read the ticket and the live API spec
(ticket_*), drive a real browser (browser_*), run API checks (api_*) and
report back to Jira and Slack (report_*).

The app under test is running at {app_url}. Use that URL for every
browser_navigate call. Do not guess other URLs.

Use only the tools of this server. Everything you need is in this text
and in those tools. Do not search the disk for a procedure or a prompt,
do not read the repository, do not run shell commands, and do not delete
or edit any file. If a tool says the app is unreachable, report that
and stop. When the report is posted, you are done.

Rules:
- Never say a check passed unless you called the tool and saw it pass.
- If a browser locator is not found, take a browser_snapshot, find the
  element with the same role and name the ticket describes, retry with
  it, and say what you replaced and why, citing the snapshot.
- If something fails and you cannot fix it, report it as a failure.

Use the test_ticket prompt for the step-by-step procedure."""

PROCEDURE = """Test ticket {ticket_id} end to end. The app under test is already running at
{app_url}. Follow these steps in order and call the tools, do not just
describe them.

1. ticket_get_ticket("{ticket_id}"). If the description has a
   Given/When/Then block, that is your test strategy. Note any locator
   from older automation (for example a button id).
2. ticket_get_openapi_spec() to see the real API endpoints.
3. Say in two or three lines which UI flow and which API endpoints cover
   the acceptance criteria.
4. Do the UI flow with the browser_* tools against {app_url}. Try the
   locator from the ticket first. If a click or type fails because the
   locator is not found: call browser_snapshot, find the element with the
   same role and accessible name the ticket means (for example a button
   named "Add Task"), retry with that element, and state the old locator,
   the new one, and the snapshot line that justified it.
5. Run the API checks with api_run_api_test for each endpoint from step
   3, with the expected status code each time.
6. Write a short summary: what passed, what failed, what was self-healed
   and why.
7. report_post_jira_comment("{ticket_id}", summary).
8. report_post_slack_message("{slack_channel}", one-line summary).

Rules: never claim a pass you did not observe; every self-heal names the
old locator, the new locator and the evidence; a failure you cannot heal
is reported as a failure."""


class Trace(Middleware):
    """One JSON line per tool call. Written by the umbrella, so every part
    is traced without knowing about it."""

    async def on_call_tool(self, context, call_next):
        name = context.message.name
        args = context.message.arguments or {}
        t0 = time.perf_counter()
        try:
            result = await call_next(context)
        except Exception as exc:  # the agent still sees the error
            self._write(name, args, t0, ok=False, summary=str(exc))
            raise
        is_error = bool(getattr(result, "is_error", False))
        self._write(name, args, t0, ok=not is_error, summary=_summary(result))
        return result

    def _write(self, name: str, args: dict, t0: float, ok: bool, summary: str) -> None:
        line = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "server": "test-mcp",
            "part": name.split("_", 1)[0],
            "tool": name,
            "args": args,
            "ok": ok,
            "ms": round((time.perf_counter() - t0) * 1000),
            "summary": summary,
        }
        TRACE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with TRACE_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, default=str) + "\n")


def _summary(result) -> str:
    """One short line describing the result, for a table cell.

    Our own tools return JSON, so show key=value pairs. Playwright returns
    markdown with ### headings, so show the Result or Error section."""
    data = getattr(result, "structured_content", None)
    if isinstance(data, dict) and data:
        inner = data.get("result", data) if set(data) == {"result"} else data
        if isinstance(inner, dict):
            pairs = [f"{k}={v}" for k, v in inner.items()
                     if isinstance(v, (str, int, float, bool)) and len(str(v)) <= 60]
            if pairs:
                return " ".join(pairs)[:160]
    for item in getattr(result, "content", None) or []:
        text = getattr(item, "text", None)
        if not text:
            continue
        return _markdown_summary(text)[:160]
    return ""


def _section(text: str, heading: str) -> str:
    """Text under a ### heading, flattened to one line, or ''."""
    if heading not in text:
        return ""
    body = text.split(heading, 1)[1].split("\n###", 1)[0]
    return " ".join(body.replace("```js", " ").replace("```", " ").split())


def _markdown_summary(text: str) -> str:
    """Playwright MCP answers in markdown sections. Pick the useful one."""
    error = _section(text, "### Error")
    if error:
        return error if error.startswith("Error") else "Error: " + error
    result = _section(text, "### Result")
    if result:
        return result
    code = _section(text, "### Ran Playwright code")
    if code:
        return code
    page = _section(text, "### Page")
    if page:
        title = page.split("Page Title:", 1)[1].split(" - ", 1)[0].strip() if "Page Title:" in page else ""
        lines = text.count("\n- ")
        return f"page '{title}', snapshot with {lines} elements"
    return " ".join(text.split())


_procs: list[subprocess.Popen] = []


def _port_free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _is_our_app(port: int) -> bool:
    """Quick check: does this port serve our task tracker's OpenAPI spec?"""
    import urllib.request
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/openapi.json", timeout=2
        ) as r:
            return r.status == 200
    except Exception:
        return False


def _kill_port_holder(port: int) -> bool:
    """Kill the process listening on port (leftover from a crashed run).

    On Windows, atexit handlers don't fire when the agent CLI kills the
    MCP server process, so uvicorn children become orphans. This cleans
    them up at the start of the next run. Returns True if the port is
    free afterwards."""
    if os.name == "nt":
        try:
            out = subprocess.check_output(
                ["netstat", "-ano", "-p", "TCP"], text=True, timeout=5,
            )
            for line in out.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    pid = line.strip().split()[-1]
                    if pid.isdigit() and int(pid) != os.getpid():
                        subprocess.run(
                            ["taskkill", "/F", "/PID", pid],
                            capture_output=True, timeout=5,
                        )
        except Exception:
            pass
    else:
        try:
            subprocess.run(["fuser", "-k", f"{port}/tcp"],
                           capture_output=True, timeout=5)
        except Exception:
            pass
    time.sleep(0.5)
    return _port_free(port)


def _find_free_port(start: int = 8000, count: int = 10) -> int:
    for port in range(start, start + count):
        if _port_free(port):
            return port
    raise RuntimeError(f"no free port in {start}-{start + count - 1}")


def _start_uvicorn(module: str, port: int) -> subprocess.Popen:
    kwargs: dict = dict(
        cwd=str(ROOT),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", module,
         "--port", str(port), "--log-level", "warning"],
        **kwargs,
    )
    deadline = time.time() + 10
    while time.time() < deadline:
        if not _port_free(port):
            return proc
        if proc.poll() is not None:
            break
        time.sleep(0.2)
    return proc


def _reset_data() -> None:
    """Clear trace and report files so each session starts fresh."""
    data_dir = ROOT / "data"
    for name in ("jira_comments.json", "slack_messages.json", "mcp_trace.jsonl"):
        (data_dir / name).unlink(missing_ok=True)


def _ensure_services() -> None:
    """Start the task tracker app and reporting dashboard.

    Kills leftover processes from a previous crashed run first, then
    starts fresh. If the preferred port is still occupied by something
    else, falls back to the next free port. Sets APP_URL and
    DASHBOARD_URL so tools resolve them at call time."""
    _reset_data()
    preferred_app = int(os.environ.get("APP_PORT", "8000"))
    preferred_dash = int(os.environ.get("DASHBOARD_PORT", "8766"))

    # Kill leftover app from a previous crashed run
    if not _port_free(preferred_app) and _is_our_app(preferred_app):
        _kill_port_holder(preferred_app)

    if _port_free(preferred_app):
        app_port = preferred_app
    else:
        app_port = _find_free_port(preferred_app + 1)
    os.environ["APP_URL"] = f"http://127.0.0.1:{app_port}"
    _procs.append(_start_uvicorn("task_tracker.main:app", app_port))

    # Kill leftover dashboard from a previous crashed run
    if not _port_free(preferred_dash):
        _kill_port_holder(preferred_dash)

    if _port_free(preferred_dash):
        dash_port = preferred_dash
    else:
        dash_port = _find_free_port(preferred_dash + 1)
    os.environ["DASHBOARD_URL"] = f"http://127.0.0.1:{dash_port}"
    _procs.append(_start_uvicorn("servers.reporting.dashboard:app", dash_port))


@atexit.register
def _stop_services() -> None:
    """Terminate all subprocesses and wait for ports to be freed."""
    for proc in _procs:
        proc.terminate()
    for proc in _procs:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
    _procs.clear()


def build_server(parts=PARTS) -> FastMCP:
    app_url = os.environ.get("APP_URL", "http://127.0.0.1:8000")
    instructions = INSTRUCTIONS_TEMPLATE.format(app_url=app_url)
    server = FastMCP("test-mcp", instructions=instructions, middleware=[Trace()])

    @server.prompt
    def test_ticket(ticket_id: str = "NASH-101") -> str:
        """Step-by-step procedure for testing one ticket with this server."""
        return PROCEDURE.format(
            ticket_id=ticket_id,
            app_url=os.environ.get("APP_URL", "http://127.0.0.1:8000"),
            slack_channel="#qa-alerts",
        )

    for module_name, prefix in parts:
        try:
            part = importlib.import_module(module_name).mcp
        except Exception as exc:  # a broken part must not take the others down
            print(f"test-mcp: part {module_name} not loaded: {exc}", file=sys.stderr)
            continue
        server.mount(part, namespace=prefix)
    return server


mcp = build_server()


if __name__ == "__main__":
    _ensure_services()
    mcp = build_server()
    mcp.run(show_banner=False)
