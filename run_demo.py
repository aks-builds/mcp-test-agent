"""One-command demo: python run_demo.py

Starts the Task Tracker app and the mock Jira/Slack dashboard, connects to
the four MCP servers over stdio, then runs the eight demo steps: read the
ticket, read the API spec, open the browser, fill and click (with the
self-heal), run the API checks, comment on Jira, post to Slack, summarise.

Every tool call goes through a real MCP client session, the same calls an
LLM agent makes when it follows AGENT_RUNBOOK.md. The decisions here are
written in code, so the run is the same every time.
"""
import argparse
import asyncio
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from contextlib import AsyncExitStack
from pathlib import Path

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent
APP_PORT = 8000
DASHBOARD_PORT = 8766
APP_URL = f"http://127.0.0.1:{APP_PORT}"
DASHBOARD_URL = f"http://127.0.0.1:{DASHBOARD_PORT}"
PLAYWRIGHT_MCP = "@playwright/mcp@0.0.83"
TICKET_ID = "NASH-101"
SLACK_CHANNEL = "#qa-alerts"

USE_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
PACE = 1.0


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text


def step(n: int, title: str) -> None:
    time.sleep(PACE)
    print()
    print(_c("1;35", f"=== STEP {n}/8  {title} ".ljust(72, "=")))


def call_line(server: str, tool: str, args: dict) -> None:
    shown = json.dumps(args) if args else ""
    if len(shown) > 90:
        shown = shown[:87] + "..."
    print(_c("36", f"  -> MCP  {server}.{tool}({shown})"))


def info(text: str) -> None:
    print(f"     {text}")


def ok(text: str) -> None:
    print(_c("32", f"  [PASS] {text}"))


def fail(text: str) -> None:
    print(_c("31", f"  [FAIL] {text}"))


def heal(text: str) -> None:
    print(_c("33", f"  [HEAL] {text}"))


# ---------------------------------------------------------------- processes

def port_free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def start_web(module: str, port: int) -> subprocess.Popen:
    if not port_free(port):
        sys.exit(f"Port {port} is already in use. Stop the old process (a leftover "
                 f"uvicorn from a rehearsal?) and run again.")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", module, "--port", str(port), "--log-level", "warning"],
        cwd=ROOT,
    )
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            httpx.get(f"http://127.0.0.1:{port}/", timeout=0.5)
            return proc
        except httpx.TransportError:
            time.sleep(0.2)
    proc.terminate()
    sys.exit(f"{module} did not start on port {port}")


def reset_mock_feeds() -> None:
    for name in ("jira_comments.json", "slack_messages.json"):
        (ROOT / "data" / name).unlink(missing_ok=True)


# ---------------------------------------------------------------- MCP

class Agent:
    def __init__(self, stack: AsyncExitStack):
        self.stack = stack
        self.sessions: dict[str, ClientSession] = {}

    async def connect(self, name: str, params: StdioServerParameters) -> None:
        read, write = await self.stack.enter_async_context(stdio_client(params))
        session = await self.stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        tools = [t.name for t in (await session.list_tools()).tools]
        self.sessions[name] = session
        if len(tools) > 6:
            listed = ", ".join(tools[:6]) + f" ... ({len(tools)} tools)"
        else:
            listed = ", ".join(tools)
        print(f"  {_c('1', name.ljust(12))} {listed}")

    async def call(self, server: str, tool: str, args: dict | None = None):
        """Call a tool. Returns (is_error, text)."""
        args = args or {}
        call_line(server, tool, args)
        result = await self.sessions[server].call_tool(tool, args)
        text = "\n".join(c.text for c in result.content if getattr(c, "type", "") == "text")
        return bool(result.isError), text

    async def call_json(self, server: str, tool: str, args: dict | None = None) -> dict:
        _, text = await self.call(server, tool, args)
        return json.loads(text)


def python_server(module: str) -> StdioServerParameters:
    env = {**os.environ, "DEMO_APP_URL": APP_URL, "PYTHONPATH": str(ROOT), "FASTMCP_LOG_LEVEL": "WARNING"}
    return StdioServerParameters(command=sys.executable, args=["-m", module], cwd=str(ROOT), env=env)


def playwright_server(headless: bool) -> StdioServerParameters:
    npx = shutil.which("npx")
    if not npx:
        sys.exit("npx not found. Install Node.js 18+ to run the Playwright MCP server.")
    args = ["-y", PLAYWRIGHT_MCP, "--isolated", "--viewport-size", "900,600"]
    if headless:
        args.append("--headless")
    return StdioServerParameters(command=npx, args=args, cwd=str(ROOT))


def find_ref(snapshot: str, role: str, name: str) -> str | None:
    m = re.search(rf'- {role} "{re.escape(name)}"[^\n]*\[ref=(e\d+)\]', snapshot)
    return m.group(1) if m else None


# ---------------------------------------------------------------- the 8 steps

async def run(headless: bool) -> bool:
    results: list[tuple[str, bool]] = []
    heals: list[str] = []

    async with AsyncExitStack() as stack:
        agent = Agent(stack)
        print(_c("1", "\nConnecting to the four MCP servers (tools each one offers):"))
        await agent.connect("ticket-spec", python_server("servers.ticket_spec.server"))
        await agent.connect("api-test", python_server("servers.api_test.server"))
        await agent.connect("reporting", python_server("servers.reporting.server"))
        await agent.connect("playwright", playwright_server(headless))

        # 1. ticket
        step(1, "Read the Jira ticket")
        ticket = await agent.call_json("ticket-spec", "get_ticket", {"ticket_id": TICKET_ID})
        info(f"{ticket['id']}: {ticket['title']}")
        description = ticket["description"]
        gwt = [line.strip() for line in description.splitlines()
               if line.strip().startswith(("Given", "When", "Then"))]
        criteria = [line.strip()[2:] for line in description.splitlines() if line.strip().startswith("- ")]
        old_locator = re.search(r"#[\w-]+", description).group(0)
        for line in gwt:
            info(_c("2", line))
        info(f"Acceptance criteria found: {len(criteria)}")
        info(f"Locator from old automation: {old_locator}")

        # 2. spec
        step(2, "Read the API spec (live OpenAPI from the app)")
        spec = await agent.call_json("ticket-spec", "get_openapi_spec")
        for path, ops in spec["paths"].items():
            info(f"{', '.join(m.upper() for m in ops):<10} {path}")
        print(_c("1", "\n  Test plan:"))
        info("UI  : type a title, click Add Task, check it shows in the list")
        info("API : POST /tasks -> 201, GET /tasks lists it, complete it -> 200,")
        info("      complete a task that does not exist -> 404")

        # 3. browser
        step(3, "Open the browser and take a snapshot")
        await agent.call("playwright", "browser_navigate", {"url": APP_URL})
        _, snap = await agent.call("playwright", "browser_snapshot")
        textbox = find_ref(snap, "textbox", "New task title")
        info(f"Snapshot: textbox 'New task title' is {textbox}")

        # 4. fill + click, self-heal
        step(4, "Fill the form and click Add Task")
        await agent.call("playwright", "browser_type",
                         {"target": textbox, "element": "New task title textbox", "text": "Buy milk"})
        is_error, text = await agent.call("playwright", "browser_click",
                                          {"target": old_locator, "element": "Add Task button"})
        if is_error:
            fail(f"Click on {old_locator} failed: {text.splitlines()[-1]}")
            info("Taking a fresh snapshot to find the button the ticket means...")
            _, snap = await agent.call("playwright", "browser_snapshot")
            button = find_ref(snap, "button", "Add Task")
            if button is None:
                fail("No button named 'Add Task' in the snapshot. Cannot self-heal.")
                results.append(("UI: Add Task adds the task to the list", False))
            else:
                note = (f"{old_locator} not found; snapshot shows button \"Add Task\" [ref={button}], "
                        f"same role and name the ticket describes")
                heal(note)
                heals.append(f"replaced {old_locator} with role=button name=\"Add Task\" "
                             f"(snapshot ref {button}) because {old_locator} no longer exists")
                await agent.call("playwright", "browser_click", {"target": button, "element": "Add Task button"})
        time.sleep(0.5)
        _, snap = await agent.call("playwright", "browser_snapshot")
        shown = re.search(r"- listitem[^\n]*Buy milk", snap) is not None
        (ok if shown else fail)("'Buy milk' is in the visible task list")
        results.append(("UI: Add Task adds the task to the list", shown))

        # 5. API
        step(5, "Run the API checks")
        checks = [
            ("POST /tasks creates a task (201)", "POST", "/tasks", {"title": "Write report"}, 201),
            ("GET /tasks lists both tasks (200)", "GET", "/tasks", None, 200),
            ("POST /tasks/1/complete marks it done (200)", "POST", "/tasks/1/complete", None, 200),
            ("Completing a missing task gives 404", "POST", "/tasks/999/complete", None, 404),
        ]
        for label, method, path, body, status in checks:
            args = {"method": method, "path": path, "expected_status": status}
            if body:
                args["body"] = body
            r = await agent.call_json("api-test", "run_api_test", args)
            passed = r["passed"]
            if path == "/tasks" and method == "GET" and passed:
                titles = [t["title"] for t in r["response_body"]]
                passed = {"Buy milk", "Write report"} <= set(titles)
                info(f"tasks returned: {titles}")
            (ok if passed else fail)(f"{label}  (got {r['actual_status']})")
            results.append((f"API: {label}", passed))

        passed_count = sum(p for _, p in results)
        all_passed = passed_count == len(results)
        verdict = "PASSED" if all_passed else "FAILED"
        heal_text = "; ".join(heals) if heals else "none"

        # 6. Jira
        step(6, "Comment on the Jira ticket")
        lines = [f"Automated test run for {TICKET_ID}: {verdict} ({passed_count}/{len(results)} checks)."]
        lines += [f"- {'PASS' if p else 'FAIL'}: {label}" for label, p in results]
        lines.append(f"Self-heal: {heal_text}.")
        await agent.call("reporting", "post_jira_comment", {"ticket_id": TICKET_ID, "comment": "\n".join(lines)})
        info(f"posted, see {DASHBOARD_URL}")

        # 7. Slack
        step(7, "Send a Slack message")
        slack = f"{TICKET_ID}: {passed_count}/{len(results)} checks passed, {len(heals)} self-heal."
        await agent.call("reporting", "post_slack_message", {"channel": SLACK_CHANNEL, "text": slack})
        info(f"posted to {SLACK_CHANNEL}")

        await agent.call("playwright", "browser_close")

        # 8. summary
        step(8, "Final summary")
        for label, p in results:
            (ok if p else fail)(label)
        for h in heals:
            heal(h)
        print()
        print(_c("1;32" if all_passed else "1;31",
                 f"  {TICKET_ID} {verdict}: {passed_count}/{len(results)} checks, {len(heals)} self-heal"))
    return all_passed


def main() -> None:
    global PACE
    sys.stdout.reconfigure(encoding="utf-8")
    if os.name == "nt":
        os.system("")  # turn on ANSI colours in the Windows console
    parser = argparse.ArgumentParser(description="Run the MCP test agent demo end to end.")
    parser.add_argument("--headless", action="store_true", help="do not show the browser window")
    parser.add_argument("--no-wait", action="store_true", help="exit at the end instead of waiting for Enter")
    parser.add_argument("--fast", action="store_true", help="no pause between steps")
    parser.add_argument("--no-dashboard", action="store_true", help="do not open the dashboard in your browser")
    opts = parser.parse_args()
    if opts.fast:
        PACE = 0

    print(_c("1", f"MCP Test Agent demo: one ticket ({TICKET_ID}) in, tested and reported result out"))
    reset_mock_feeds()
    procs = [start_web("demo_app.main:app", APP_PORT), start_web("servers.reporting.dashboard:app", DASHBOARD_PORT)]
    print(f"  Task Tracker app   {APP_URL}")
    print(f"  Jira/Slack mock    {DASHBOARD_URL}  (cleared)")
    if not opts.no_dashboard:
        webbrowser.open(DASHBOARD_URL)
    try:
        all_passed = asyncio.run(run(opts.headless))
        if not opts.no_wait and sys.stdin.isatty():
            input(f"\nDashboard is still live at {DASHBOARD_URL}. Press Enter to stop... ")
    finally:
        for p in procs:
            p.terminate()
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
