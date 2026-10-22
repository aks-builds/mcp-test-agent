# MCP Test Agent

Demo for the NashLearn session "Building Test Agents with MCP Servers"
(23 Oct 2026). One Jira ticket goes in. The agent reads it, reads the live
API spec, tests the UI in a real browser, heals a broken locator, runs the
API checks, and reports back to Jira and Slack. Nobody presses a button in
between.

![Demo flow](docs/demo-flow.svg)

## One server, four parts

The agent talks to one MCP server, `test-mcp`. Inside it are four parts.
Three are ours, one is Microsoft's Playwright MCP passed straight through.

| Part | Tools the agent sees | Where it lives |
|---|---|---|
| ticket | `ticket_get_ticket`, `ticket_get_openapi_spec` | `servers/ticket_spec/server.py` |
| api | `api_run_api_test` | `servers/api_test/server.py` |
| report | `report_post_jira_comment`, `report_post_slack_message` | `servers/reporting/server.py` |
| browser | `browser_navigate`, `browser_snapshot`, `browser_click`, ... (25 tools) | `servers/browser/server.py` (proxy to `npx @playwright/mcp`) |

`servers/test_mcp/server.py` is the umbrella. It mounts each part under
its prefix, ships the test procedure as the server's `instructions` and
as an MCP prompt called `test_ticket`, and writes one line per tool call
to `data/mcp_trace.jsonl`. There are no instruction files, skills or
plugins in this repo. Tools, procedure and trace all come from MCP.

### Adding a part

1. Write a module that exposes a FastMCP object called `mcp` (copy
   `servers/reporting/server.py` for your own tools, or
   `servers/browser/server.py` to pull in someone else's MCP server).
2. Add one line to `PARTS` in `servers/test_mcp/server.py`:
   `("servers.my_part.server", "my")`.
3. Restart the agent. It now sees `my_*` tools, and they are traced.

A part that fails to load is reported on stderr and skipped. The other
parts keep working.

## Run it with one command

```bash
pip install -r requirements.txt
python run_demo.py --agent opencode     # or claude, gemini, codex
```

Needs Python 3.11+ and Node.js 18+ (for `npx @playwright/mcp`). The first
run downloads the Playwright MCP package, so do it once before going live.

This starts the Task Tracker app on port 8000 and the mock Jira/Slack
dashboard on port 8766, opens the dashboard, opens a second console with
the live MCP trace, and launches the agent you picked with the first
message already typed:

```
Test ticket NASH-101 end to end with the test-mcp tools. Follow the test-mcp
server instructions step by step, call the tools for real, and report to
Jira and Slack at the end.
```

The trace window shows every call as `test-mcp` sees it:

```
  #  time (UTC)   hop                        call                                       result
  1  03:53:03.319 agent -> test-mcp/ticket   ticket_get_ticket NASH-101                 ok   id=NASH-101 title=Add Task creation flow should work end-to-end
  2  03:53:03.454 agent -> test-mcp/ticket   ticket_get_openapi_spec                    ok   openapi=3.1.0
  3  03:53:04.194 agent -> test-mcp/browser  browser_navigate http://127.0.0.1:8000     ok   await page.goto('http://127.0.0.1:8000');
  4  03:53:04.217 agent -> test-mcp/browser  browser_snapshot                           ok   page 'Task Tracker', snapshot with 4 elements
  5  03:53:04.262 agent -> test-mcp/browser  browser_type e3 New task title textbox ... ok   await page.getByRole('textbox', { name: 'New task title' }).fill('Buy
  6  03:53:04.281 agent -> test-mcp/browser  browser_click #add-task-btn Add Task bu... FAIL Error: "#add-task-btn" does not match any elements.
  7  03:53:04.304 agent -> test-mcp/browser  browser_snapshot                           ok   page 'Task Tracker', snapshot with 4 elements
  8  03:53:05.395 agent -> test-mcp/browser  browser_click e4 Add Task button           ok   await page.getByRole('button', { name: 'Add Task' }).click();
 10  03:53:05.935 agent -> test-mcp/api      api_run_api_test POST /tasks 201 {'titl... ok   passed=True method=POST path=/tasks expected_status=201 actual_status=
 14  03:53:06.054 agent -> test-mcp/report   report_post_jira_comment NASH-101 Autom... ok   posted=True ticket_id=NASH-101
 15  03:53:06.065 agent -> test-mcp/report   report_post_slack_message #qa-alerts NA... ok   posted=True channel=#qa-alerts
```

The planted drift: the ticket still names the button `#add-task-btn` from
older automation, but the app now uses `save-task-btn`. Its label is still
"Add Task", which is what the agent finds in the snapshot.

### Scripted run (rehearsal and fallback)

```bash
python run_demo.py
```

Same services, same MCP calls, but the decisions are written in code, so
it runs the same way every time. It prints the eight steps and ends with
the same trace table. Exit code is 0 only when every check passed.

Options: `--headless` (no browser window), `--fast` (no pause between
steps), `--no-dashboard`, `--no-wait`, `--no-trace-window`, and
`--trace` to show only the live table (what the second window runs).

### Which agent, which file

Each tool reads its own config file. All four point at the same one
server, and a unit test keeps them identical.

| Tool | Config file | Start it yourself with |
|---|---|---|
| Claude Code | `.mcp.json` | `claude` |
| Gemini CLI | `.gemini/settings.json` | `gemini` |
| Codex CLI | `.codex/config.toml` | `codex` |
| OpenCode | `opencode.json` | `opencode` |

First-run notes:

- Always start the tool inside this folder. Project MCP config is not
  loaded from anywhere else.
- Claude Code asks you to approve the project server once.
- Gemini CLI and Codex CLI load project MCP config only from a trusted
  folder, and ask you to trust it the first time. To check, run
  `gemini mcp list` or `codex mcp list` here: `test-mcp` should show as
  connected (Gemini) or enabled (Codex).
- OpenCode needs no trust step. Pick a capable model with `/models`
  before the demo; the free default is not enough for the self-heal step.
- Every tool asks before each MCP tool call unless you let it run on its
  own. In Claude Code pick "always allow" on the first prompt. Gemini has
  `gemini -y`, Codex has `codex --full-auto`. Decide beforehand whether
  you want to approve each call by hand on stage or let it run.
- If a port is already in use (a leftover uvicorn from a rehearsal), stop
  that process first.

## Layout

```
run_demo.py               one command: services + trace window + agent (or scripted run)
servers/test_mcp/         the umbrella: PARTS list, instructions, test_ticket prompt, trace
servers/ticket_spec/      part "ticket": get_ticket, get_openapi_spec
servers/api_test/         part "api": run_api_test
servers/reporting/        part "report": post_jira_comment, post_slack_message + dashboard
servers/browser/          part "browser": proxy to Microsoft's Playwright MCP
data/tickets.json         the mock Jira ticket NASH-101
data/mcp_trace.jsonl      one line per tool call (written by test-mcp, cleared each run)
demo_app/                 Task Tracker app under test (FastAPI + one HTML page)
.mcp.json, .gemini/settings.json, .codex/config.toml, opencode.json
                          the same one server, for each agent tool
tests/                    unit tests and end-to-end tests
```

## Tests

```bash
pytest tests/unit
pytest tests/integration
```

`tests/integration/test_run_demo.py` runs `run_demo.py --headless` end to
end through `test-mcp`, so it needs Node.js and network access the first
time.
