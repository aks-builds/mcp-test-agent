"""One command to run the test agent.

    python run.py                  scripted run: same MCP calls, decisions in code
    python run.py --agent opencode live run: a real agent (claude, gemini, codex, opencode)
    python run.py --trace          live table of every MCP call, for a second window

Both runs start the Task Tracker app and the mock Jira/Slack dashboard,
then talk to ONE MCP server, test-mcp, which has four parts inside:
ticket, api, report and browser (Playwright). Every tool call passes
through test-mcp, which writes one line per call to data/mcp_trace.jsonl.
That file is what the trace table shows.
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
from pathlib import Path

import httpx
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from fastmcp.exceptions import ToolError

ROOT = Path(__file__).resolve().parent
APP_PORT = 8000
DASHBOARD_PORT = 8766
APP_URL = f"http://127.0.0.1:{APP_PORT}"
DASHBOARD_URL = f"http://127.0.0.1:{DASHBOARD_PORT}"
SERVER_NAME = "test-mcp"
TRACE_FILE = ROOT / "data" / "mcp_trace.jsonl"
TICKET_ID = "NASH-101"
SLACK_CHANNEL = "#qa-alerts"

# One line, no quotes or newlines, so it passes cleanly through any shell.
# The full procedure comes from the server itself (its instructions and
# its test_ticket prompt), not from a file in this repo.
LAUNCH_PROMPT = (f"Test ticket {TICKET_ID} end to end with the {SERVER_NAME} tools. "
                 f"Follow the {SERVER_NAME} server instructions step by step, "
                 f"call the tools for real, and report to Jira and Slack at the end.")

# Each agent is started so that it can only act through test-mcp: no
# shell, no file edits, no plugins. Gemini has no such switch, so it
# relies on the server instructions alone.
AGENTS = {
    "claude": lambda prompt: ["claude", "--disallowedTools", "Bash,Edit,Write,NotebookEdit", prompt],
    "gemini": lambda prompt: ["gemini", "-i", prompt],
    "codex": lambda prompt: ["codex", "--sandbox", "read-only", prompt],
    "opencode": lambda prompt: ["opencode", "--pure", "--prompt", prompt],
}

USE_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
PACE = 1.0


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text


def step(n: int, title: str) -> None:
    time.sleep(PACE)
    print()
    print(_c("1;35", f"=== STEP {n}/8  {title} ".ljust(72, "=")))


def call_line(tool: str, args: dict) -> None:
    shown = json.dumps(args) if args else ""
    if len(shown) > 90:
        shown = shown[:87] + "..."
    print(_c("36", f"  -> MCP  {SERVER_NAME}.{tool}({shown})"))


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
                 f"uvicorn from an earlier run?) and run again.")
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
    for name in ("jira_comments.json", "slack_messages.json", "mcp_trace.jsonl"):
        (ROOT / "data" / name).unlink(missing_ok=True)


def start_services(open_dashboard: bool) -> list[subprocess.Popen]:
    reset_mock_feeds()
    procs = [start_web("task_tracker.main:app", APP_PORT),
             start_web("servers.reporting.dashboard:app", DASHBOARD_PORT)]
    print(f"  Task Tracker app   {APP_URL}")
    print(f"  Jira/Slack mock    {DASHBOARD_URL}  (cleared)")
    print(f"  MCP trace          {TRACE_FILE.relative_to(ROOT)}  (cleared)")
    if open_dashboard:
        webbrowser.open(DASHBOARD_URL)
    return procs


# ---------------------------------------------------------------- MCP trace table

def _hop(row: dict) -> str:
    return f"agent -> {row.get('server', SERVER_NAME)}/{row.get('part', '?')}"


def _call(row: dict) -> str:
    args = row.get("args") or {}
    values = " ".join(str(v) for v in args.values())
    text = f"{row['tool']} {values}".strip()
    return text if len(text) <= 42 else text[:39] + "..."


def _result(row: dict) -> str:
    mark = "ok  " if row.get("ok") else "FAIL"
    summary = row.get("summary") or ""
    return f"{mark} {summary[:70]}".rstrip()


def trace_header() -> None:
    print(_c("1", f"{'#':>3}  {'time (UTC)':<12} {'hop':<26} {'call':<42} result"))


def trace_row(n: int, row: dict) -> None:
    clock = row["ts"][11:23]
    colour = "32" if row.get("ok") else "31"
    print(f"{n:>3}  {clock:<12} {_hop(row):<26} {_call(row):<42} {_c(colour, _result(row))}")


def read_trace() -> list[dict]:
    if not TRACE_FILE.exists():
        return []
    return [json.loads(line) for line in TRACE_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]


def print_trace_table() -> None:
    rows = read_trace()
    print(_c("1", f"\n  MCP trace: {len(rows)} calls, all through {SERVER_NAME}"))
    trace_header()
    for n, row in enumerate(rows, 1):
        trace_row(n, row)


def tail_trace() -> None:
    """Keep printing new trace rows as they land. Ctrl+C to stop."""
    print(_c("1", f"Every MCP call the agent makes, as {SERVER_NAME} sees it. Waiting...\n"))
    trace_header()
    offset, seen = 0, 0
    try:
        while True:
            if TRACE_FILE.exists():
                size = TRACE_FILE.stat().st_size
                if size < offset:  # a new run cleared the file
                    offset, seen = 0, 0
                    print()
                    trace_header()
                if size > offset:
                    with TRACE_FILE.open("r", encoding="utf-8") as f:
                        f.seek(offset)
                        chunk = f.read()
                        offset = f.tell()
                    for line in chunk.splitlines():
                        if line.strip():
                            seen += 1
                            trace_row(seen, json.loads(line))
            time.sleep(0.3)
    except KeyboardInterrupt:
        pass


def open_trace_window() -> None:
    if os.name == "nt":
        subprocess.Popen(["cmd", "/c", "start", "MCP trace", sys.executable, str(ROOT / "run.py"), "--trace"],
                         cwd=ROOT)
        print("  Trace window opened (every MCP call, live)")
    else:
        print(f"  In another terminal run: python run.py --trace")


# ---------------------------------------------------------------- MCP client

def server_transport(headless: bool) -> StdioTransport:
    env = {**os.environ, "APP_URL": APP_URL, "PYTHONPATH": str(ROOT), "FASTMCP_LOG_LEVEL": "WARNING"}
    if headless:
        env["PLAYWRIGHT_HEADLESS"] = "1"
    return StdioTransport(sys.executable, ["-m", "servers.test_mcp.server"], env=env, cwd=str(ROOT))


class Agent:
    """The scripted stand-in for an LLM agent: same MCP calls, decisions in code."""

    def __init__(self, client: Client):
        self.client = client

    async def call(self, tool: str, args: dict | None = None) -> tuple[bool, str]:
        """Call a tool. Returns (is_error, text)."""
        args = args or {}
        call_line(tool, args)
        try:
            result = await self.client.call_tool(tool, args, raise_on_error=False)
        except ToolError as exc:
            return True, str(exc)
        text = "\n".join(c.text for c in result.content if getattr(c, "text", None))
        return bool(result.is_error), text

    async def call_json(self, tool: str, args: dict | None = None) -> dict:
        _, text = await self.call(tool, args)
        return json.loads(text)


def find_ref(snapshot: str, role: str, name: str) -> str | None:
    m = re.search(rf'- {role} "{re.escape(name)}"[^\n]*\[ref=(e\d+)\]', snapshot)
    return m.group(1) if m else None


# ---------------------------------------------------------------- the 8 steps

async def run(headless: bool) -> bool:
    results: list[tuple[str, bool]] = []
    heals: list[str] = []

    async with Client(server_transport(headless)) as client:
        agent = Agent(client)
        tools = [t.name for t in await client.list_tools()]
        parts: dict[str, list[str]] = {}
        for name in tools:
            parts.setdefault(name.split("_", 1)[0], []).append(name)
        print(_c("1", f"\nConnected to {SERVER_NAME}: {len(tools)} tools in {len(parts)} parts"))
        for part, names in parts.items():
            listed = ", ".join(names[:4]) + (f" ... ({len(names)} tools)" if len(names) > 4 else "")
            print(f"  {_c('1', part.ljust(8))} {listed}")

        # 1. ticket
        step(1, "Read the Jira ticket")
        ticket = await agent.call_json("ticket_get_ticket", {"ticket_id": TICKET_ID})
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
        spec = await agent.call_json("ticket_get_openapi_spec")
        for path, ops in spec["paths"].items():
            info(f"{', '.join(m.upper() for m in ops):<10} {path}")
        print(_c("1", "\n  Test plan:"))
        info("UI  : type a title, click Add Task, check it shows in the list")
        info("API : POST /tasks -> 201, GET /tasks lists it, complete it -> 200,")
        info("      complete a task that does not exist -> 404")

        # 3. browser
        step(3, "Open the browser and take a snapshot")
        await agent.call("browser_navigate", {"url": APP_URL})
        _, snap = await agent.call("browser_snapshot")
        textbox = find_ref(snap, "textbox", "New task title")
        info(f"Snapshot: textbox 'New task title' is {textbox}")

        # 4. fill + click, self-heal
        step(4, "Fill the form and click Add Task")
        await agent.call("browser_type",
                         {"target": textbox, "element": "New task title textbox", "text": "Buy milk"})
        is_error, text = await agent.call("browser_click",
                                          {"target": old_locator, "element": "Add Task button"})
        if is_error:
            fail(f"Click on {old_locator} failed: {text.splitlines()[-1]}")
            info("Taking a fresh snapshot to find the button the ticket means...")
            _, snap = await agent.call("browser_snapshot")
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
                await agent.call("browser_click", {"target": button, "element": "Add Task button"})
        time.sleep(0.5)
        _, snap = await agent.call("browser_snapshot")
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
            r = await agent.call_json("api_run_api_test", args)
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
        await agent.call("report_post_jira_comment", {"ticket_id": TICKET_ID, "comment": "\n".join(lines)})
        info(f"posted, see {DASHBOARD_URL}")

        # 7. Slack
        step(7, "Send a Slack message")
        slack = f"{TICKET_ID}: {passed_count}/{len(results)} checks passed, {len(heals)} self-heal."
        await agent.call("report_post_slack_message", {"channel": SLACK_CHANNEL, "text": slack})
        info(f"posted to {SLACK_CHANNEL}")

        await agent.call("browser_close")

        # 8. summary
        step(8, "Final summary")
        for label, p in results:
            (ok if p else fail)(label)
        for h in heals:
            heal(h)
        print()
        print(_c("1;32" if all_passed else "1;31",
                 f"  {TICKET_ID} {verdict}: {passed_count}/{len(results)} checks, {len(heals)} self-heal"))
    print_trace_table()
    return all_passed


# ---------------------------------------------------------------- live agent

def run_agent(name: str) -> int:
    exe = shutil.which(name)
    if not exe:
        sys.exit(f"{name} is not installed or not on PATH.")
    print(_c("1", f"\nStarting {name}. The first message is already typed for you:"))
    print(f"  {LAUNCH_PROMPT}\n")
    cmd = [exe, *AGENTS[name](LAUNCH_PROMPT)[1:]]
    return subprocess.call(cmd, cwd=ROOT)


# ---------------------------------------------------------------- main

def main() -> None:
    global PACE
    sys.stdout.reconfigure(encoding="utf-8")
    if os.name == "nt":
        os.system("")  # turn on ANSI colours in the Windows console
    parser = argparse.ArgumentParser(description="Run the MCP test agent end to end.")
    parser.add_argument("--agent", choices=sorted(AGENTS), help="run a real agent instead of the scripted steps")
    parser.add_argument("--trace", action="store_true", help="only show the live MCP call table (second window)")
    parser.add_argument("--headless", action="store_true", help="do not show the browser window")
    parser.add_argument("--no-wait", action="store_true", help="exit at the end instead of waiting for Enter")
    parser.add_argument("--fast", action="store_true", help="no pause between steps")
    parser.add_argument("--no-dashboard", action="store_true", help="do not open the dashboard in your browser")
    parser.add_argument("--no-trace-window", action="store_true", help="with --agent: do not open the trace window")
    opts = parser.parse_args()
    if opts.fast:
        PACE = 0

    if opts.trace:
        tail_trace()
        return

    mode = f"live agent: {opts.agent}" if opts.agent else "scripted"
    print(_c("1", f"MCP Test Agent ({mode}): one ticket ({TICKET_ID}) in, tested and reported result out"))
    procs = start_services(open_dashboard=not opts.no_dashboard)
    try:
        if opts.agent:
            if not opts.no_trace_window:
                open_trace_window()
            run_agent(opts.agent)
            print_trace_table()
            all_passed = True
        else:
            all_passed = asyncio.run(run(opts.headless))
        if not opts.no_wait and sys.stdin.isatty():
            input(f"\nDashboard is still live at {DASHBOARD_URL}. Press Enter to stop... ")
    finally:
        for p in procs:
            p.terminate()
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
