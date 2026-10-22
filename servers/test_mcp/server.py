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
import importlib
import json
import os
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

INSTRUCTIONS = """You are a test agent. This server gives you everything you need to test
one Jira ticket end to end: read the ticket and the live API spec
(ticket_*), drive a real browser (browser_*), run API checks (api_*) and
report back to Jira and Slack (report_*).

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


def build_server(parts=PARTS) -> FastMCP:
    server = FastMCP("test-mcp", instructions=INSTRUCTIONS, middleware=[Trace()])

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
    mcp.run(show_banner=False)
