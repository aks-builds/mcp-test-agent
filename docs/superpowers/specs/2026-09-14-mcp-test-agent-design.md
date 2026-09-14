# MCP Test Agent — Design Spec

**Status:** Approved for planning (2026-09-14)
**Sub-project:** 1 of 2 for the NashLearn session "Building Test Agents with MCP Servers"
**Target session date:** 23 October 2026 (45-minute NashLearn live session)

## Context

This is the demo tool behind the next NashLearn/NashKnolx session, "Building Test
Agents with MCP Servers." It follows the same overall production pattern as the
June 2026 "AI-Assisted Test Failure Analysis" session (`C:\NashTech\ai-test-failure-analyzer`
+ `C:\NashTech\nashlearn-session-materials`): build the real tool first, then build
the deck, spatially-mapped speaker transcript, live-demo run-book, and FAQ around it.

This spec covers **sub-project 1 only: the tool**. Sub-project 2 (deck, transcript,
demo run-book, FAQ) gets its own spec once the tool exists and its actual behavior
is known, matching how the June session's materials were built around the finished
analyzer rather than in parallel with it.

**Core thesis of the topic:** moving from manually-triggered automation to
self-directed, agentic testing — demonstrated by showing one agent orchestrate
several narrow, independently testable MCP servers instead of one monolithic
script. MCP itself (the protocol boundary, tool discovery, composability) is the
spine of the talk, not a supporting detail — unlike the June session where MCP
was one slide among twenty.

## Demo narrative

Agent reads a Jira ticket and an OpenAPI spec, plans a test strategy, executes
tests via Playwright MCP (browser) and a custom API-Test MCP (terminal/HTTP),
self-heals when a UI locator has drifted, then reports results back to Jira and
Slack automatically.

## Components

| Server | Origin | Role | Key tools |
|---|---|---|---|
| Playwright MCP | Official, unmodified (Node, spawned via `npx`) | Browser-level test execution | `navigate`, `snapshot`, `click`, `fill`, assertions |
| Ticket/Spec MCP | Built (Python) | Surfaces the mock Jira ticket + OpenAPI spec | `get_ticket(id)`, `get_openapi_spec()` |
| API-Test MCP | Built (Python) | Executes + asserts HTTP calls against the spec | `run_api_test(request)` — deterministic status/schema checks, no LLM judgment |
| Reporting MCP | Built (Python) | Writes results back to the mock endpoints | `post_jira_comment(ticket_id, comment)`, `post_slack_message(channel, text)` |

One orchestrating agent (Claude Code, or any MCP-capable client) calls tools
across all four servers over stdio. No server is remotely hosted for the demo;
streamable-HTTP deployment is mentioned as a single talking-point slide only
("same server, different transport, for when a team or CI needs to share it") —
nothing on stage depends on network reachability.

**Explicitly out of scope for this build:**
- Real Jira Cloud / real Slack workspace integration
- Remote/streamable-HTTP hosting of any of the four servers
- Root-cause re-diagnosis / re-planning on failure (the "re-plan" adaptation
  mode from the design discussion was not chosen — this build implements
  self-healing only)
- Enforcing a strict Given/When/Then ticket format — the ticket parser treats
  G/W/T as optional structure; a plain-prose ticket still produces a usable
  test strategy, just with the agent doing more characterization work itself

## Target demo app (new, purpose-built)

A small FastAPI service with a minimal web UI, built specifically for this demo.

- FastAPI's auto-generated `/openapi.json` is the spec the Ticket/Spec MCP
  serves — the spec can never drift from the code, keeping the "deterministic,
  grounded" thesis honest (no hand-maintained spec to go stale).
- One planted bug: a UI element's `id`/`data-testid` is renamed between when
  the ticket was written and when the test runs, but its accessible role/name
  (e.g. a button labeled "Submit") is unchanged. This is the concrete hook for
  the self-heal moment.
- Runs entirely locally (`uvicorn`), no external dependency.

## Self-heal mechanism

1. Playwright MCP action fails against the old (planted-stale) locator.
2. Agent calls Playwright MCP's `snapshot` tool to get the current accessibility
   tree.
3. Agent finds the same role/name at its new location in the snapshot.
4. Agent retries the action with the corrected locator and logs what changed
   and why, citing the snapshot as evidence.

This mirrors the "no citation, no claim" discipline from the analyzer FAQ: the
fix is grounded in an actual tool-returned DOM snapshot, not a guess.

## Data flow (the live demo path)

1. Ticket/Spec MCP → agent reads the mock ticket + OpenAPI spec.
2. Agent drafts a test strategy (the one genuinely non-deterministic,
   LLM-reasoning step in the pipeline).
3. Playwright MCP executes the UI flow, hits the planted locator break,
   self-heals per above.
4. API-Test MCP executes and asserts HTTP calls against the spec
   (deterministic pass/fail, no model judgment involved in the assertion
   itself).
5. Reporting MCP posts a results comment to the mock Jira ticket and a summary
   to the mock Slack channel.
6. A small local dashboard renders the mock Jira comment thread and Slack feed
   updating live as step 5 happens — visual payoff equivalent to a real
   integration, with zero external risk.

Because both report targets are already local mocks (not real third-party
accounts), the Reporting MCP writes go through immediately — there is no
`dry_run` gate here, unlike the analyzer's real-GitHub issue path, since there
is no real external side effect to protect against.

## Testing strategy (for the tool itself)

- TDD per MCP server (pytest) — each of the three built servers gets unit
  coverage for its tools independent of the others.
- One full ordered integration test that replays the entire demo path
  end-to-end deterministically against the target demo app. This is what makes
  the live demo safe to run on stage: it is a proven, passing script, not an
  improvisation, matching the reliability discipline of the June session's
  demo run-book.

## Repo layout (proposed)

```
C:\NashTech\mcp-test-agent\
  demo_app\              # FastAPI service + minimal web UI, planted locator bug
  servers\
    ticket_spec\          # Ticket/Spec MCP (Python, MCP SDK)
    api_test\              # API-Test MCP (Python, MCP SDK)
    reporting\             # Reporting MCP (Python, MCP SDK) + local dashboard
  tests\
    unit\                 # per-server pytest suites
    integration\           # full end-to-end replay test
  docs\superpowers\specs\  # this file, and future specs
```

## Success criteria

- The full end-to-end flow (ticket + spec → strategy → UI execution with
  self-heal → API execution → reporting) completes deterministically in the
  integration test, with zero external network calls beyond spawning local
  processes (Playwright MCP via `npx`, the three built servers, the demo app).
- All four MCP servers are independently startable/testable — no server
  depends on another's internals, only on the shared demo app and mock data
  stores.
- Session materials (sub-project 2) can be built entirely by observing this
  tool's real behavior, same as the June precedent.
