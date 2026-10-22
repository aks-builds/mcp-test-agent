"""Draws docs/demo-flow.svg. Run: python docs/make_demo_flow.py

One agent, one server (test-mcp) with four parts inside, the app under
test, the mock Jira/Slack dashboard, and the trace window.
"""
from pathlib import Path

OUT = Path(__file__).with_name("demo-flow.svg")
W, H = 2000, 1010

INK, GREY, BLUE, ORANGE, PURPLE = "#1d2230", "#5f6673", "#2f5fbf", "#e8743b", "#6b5bd2"
BG, PANEL, PANEL_EDGE = "#f6f6f6", "#ececee", "#dcdce0"
FONT = "Consolas, 'JetBrains Mono', 'Courier New', monospace"
SANS = "'Segoe UI', Arial, sans-serif"

parts: list[str] = []


def add(s: str) -> None:
    parts.append(s)


def container(x, y, w, h, label):
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="{PANEL}" stroke="{PANEL_EDGE}" stroke-width="2"/>')
    pill_w = 18 + 8.2 * len(label)
    cx = x + w / 2
    add(f'<rect x="{cx - pill_w / 2:.1f}" y="{y - 11}" width="{pill_w:.1f}" height="22" rx="4" fill="{BG}" stroke="#cfd0d6"/>')
    add(f'<text x="{cx:.1f}" y="{y + 4}" text-anchor="middle" font-family="{FONT}" font-size="12" '
        f'letter-spacing="1.6" fill="{GREY}">{label}</text>')


def umbrella(x, y, w, h, label):
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="#e8eefb" stroke="{BLUE}" stroke-width="2.4"/>')
    pill_w = 18 + 9.2 * len(label)
    cx = x + w / 2
    add(f'<rect x="{cx - pill_w / 2:.1f}" y="{y - 11}" width="{pill_w:.1f}" height="22" rx="4" fill="#fff" stroke="{BLUE}"/>')
    add(f'<text x="{cx:.1f}" y="{y + 4}" text-anchor="middle" font-family="{FONT}" font-size="12" font-weight="700" '
        f'letter-spacing="1.6" fill="{BLUE}">{label}</text>')


def box(x, y, w, h, tag, title, lines, fill="#ffffff", edge=INK, tag_colour=None, dashed=False):
    tag_colour = tag_colour or edge
    dash = ' stroke-dasharray="8 6"' if dashed else ""
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" stroke="{edge}" stroke-width="2"{dash}/>')
    tw = 18 + 8.2 * len(tag)
    add(f'<rect x="{x + 20}" y="{y + 18}" width="{tw:.1f}" height="22" rx="4" fill="#fff" stroke="{tag_colour}" stroke-width="1.2"/>')
    add(f'<text x="{x + 29}" y="{y + 34}" font-family="{FONT}" font-size="12" letter-spacing="1.2" fill="{tag_colour}">{tag}</text>')
    add(f'<text x="{x + 20}" y="{y + 72}" font-family="{SANS}" font-size="23" font-weight="700" fill="{INK}">{title}</text>')
    for i, line in enumerate(lines):
        add(f'<text x="{x + 20}" y="{y + 98 + 21 * i}" font-family="{SANS}" font-size="14" fill="#3a3f4b">{line}</text>')


def arrow(points, colour, dashed=False, marker=True):
    d = "M " + " L ".join(f"{px} {py}" for px, py in points)
    dash = ' stroke-dasharray="7 6"' if dashed else ""
    m = f' marker-end="url(#a-{colour})"' if marker else ""
    add(f'<path d="{d}" fill="none" stroke="{COLOURS[colour]}" stroke-width="2.4"{dash}{m}/>')


def label(x, y, text, colour, anchor="start"):
    w = 12 + 8.4 * len(text)
    rx = x - 6 if anchor == "start" else x - w / 2
    add(f'<rect x="{rx:.1f}" y="{y - 14}" width="{w:.1f}" height="20" fill="{BG}"/>')
    add(f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="{FONT}" font-size="12.5" font-weight="700" '
        f'letter-spacing="1.3" fill="{COLOURS[colour]}">{text}</text>')


COLOURS = {"blue": BLUE, "orange": ORANGE, "purple": PURPLE, "grey": GREY, "ink": INK}

# ------------------------------------------------------------------ canvas
add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
add("<defs>")
add('<pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1.1" fill="#d4d4da"/></pattern>')
for name, col in COLOURS.items():
    add(f'<marker id="a-{name}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" '
        f'orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="{col}"/></marker>')
add("</defs>")
add(f'<rect width="{W}" height="{H}" fill="{BG}"/><rect width="{W}" height="{H}" fill="url(#dots)"/>')

# ------------------------------------------------------------------ containers
container(40, 90, 390, 150, "MOCK JIRA . TICKETS")
umbrella(600, 90, 740, 695, "TEST-MCP . ONE SERVER")
container(1470, 170, 440, 390, "TASK TRACKER APP . :8000")
container(1470, 680, 440, 290, "MOCK JIRA + SLACK . :8766")

# ------------------------------------------------------------------ arrows (under boxes)
# ticket file -> ticket part
arrow([(410, 167), (520, 167), (520, 195), (636, 195)], "grey")
label(430, 190, "READS TICKET", "grey")
# agent -> test-mcp
arrow([(410, 425), (596, 425)], "blue")
label(430, 397, "MCP OVER STDIO", "blue")
label(430, 452, "ONE CONNECTION . 30 TOOLS", "blue")
# ticket part -> live openapi spec (over the top)
arrow([(805, 140), (805, 115), (1440, 115), (1440, 430), (1486, 430)], "grey")
label(1230, 100, "READS LIVE OPENAPI SPEC", "grey", anchor="middle")
# browser part -> UI
arrow([(1320, 195), (1380, 195), (1380, 250), (1486, 250)], "orange")
# api part -> API (through the row gap)
arrow([(805, 335), (805, 300), (1420, 300), (1420, 470), (1486, 470)], "orange")
label(820, 291, "HTTP CALL + STATUS CHECK", "orange")
# report part -> jira + slack
arrow([(1320, 390), (1400, 390), (1400, 770), (1486, 770)], "grey")
arrow([(1400, 770), (1400, 895), (1486, 895)], "grey")
label(1325, 377, "WRITES", "grey")
# trace -> trace window
arrow([(972, 760), (972, 805), (414, 805)], "purple", dashed=True)
label(690, 797, "ONE LINE PER CALL . LIVE TABLE", "purple")

# ------------------------------------------------------------------ left column
box(60, 110, 350, 115, "TICKET", "NASH-101",
    ["data/tickets.json, Given / When / Then optional"])
box(60, 330, 350, 190, "AGENT", "Test agent",
    ["Claude Code . Gemini CLI . Codex . OpenCode",
     "or run_demo.py (scripted, one command)",
     "sees one server, one tool list, one plan",
     "plan . act . observe . adapt"],
    fill=PANEL, edge=GREY, tag_colour=INK)
box(60, 700, 350, 215, "TRACE WINDOW", "Every MCP call, live",
    ["#  time  hop  call  result",
     "red row: click on #add-task-btn fails",
     "next two rows: snapshot, click by name",
     "that is the self-heal, in three lines",
     "data/mcp_trace.jsonl"],
    fill="#e9e5fb", edge=PURPLE)

# ------------------------------------------------------------------ inside the umbrella
box(640, 140, 330, 125, "PART . TICKET", "Read ticket and spec",
    ["ticket_get_ticket", "ticket_get_openapi_spec"], fill="#fde3d7", edge=ORANGE)
box(990, 140, 330, 125, "PART . BROWSER", "Drive the browser",
    ["browser_navigate . snapshot . type . click", "Microsoft Playwright MCP, passed through"],
    fill="#fde3d7", edge=ORANGE)
box(640, 335, 330, 125, "PART . API", "Run the API checks",
    ["api_run_api_test", "expected status vs actual status"], fill="#fde3d7", edge=ORANGE)
box(990, 335, 330, 125, "PART . REPORT", "Report back",
    ["report_post_jira_comment", "report_post_slack_message"], fill="#fde3d7", edge=ORANGE)
box(640, 485, 680, 75, "+ YOUR NEXT PART", "",
    [], fill="#f3f6fd", edge=BLUE, dashed=True)
add(f'<text x="840" y="516" font-family="{SANS}" font-size="16" fill="{BLUE}">'
    f'any FastMCP, yours or someone else\'s: one file in servers/, one line in PARTS</text>')
add(f'<text x="840" y="539" font-family="{SANS}" font-size="14" fill="#3a3f4b">'
    f'the agent sees it on the next start, the four agent configs do not change</text>')

box(640, 585, 215, 175, "INSTRUCTIONS", "The plan",
    ["eight steps, three rules,", "sent to every agent", "the moment it connects.", "no .md, no skill, no plugin"],
    fill="#ffffff", edge=INK)
box(865, 585, 215, 175, "TRACE", "One line per call",
    ["written here, so every", "part is traced for free", "-> data/mcp_trace.jsonl"],
    fill="#e9e5fb", edge=PURPLE)
box(1090, 585, 230, 175, "PARTS LIST", "Four lines",
    ["each part mounted under", "its prefix. a broken part", "is skipped, the rest", "keep working"],
    fill="#ffffff", edge=INK)

# ------------------------------------------------------------------ right column
box(1490, 195, 400, 150, "UI . /", "Add Task form",
    ["button id is now save-task-btn", "ticket still says #add-task-btn"])
box(1490, 385, 400, 150, "API . FASTAPI", "/tasks",
    ["POST . GET . /{id}/complete", "/openapi.json"])
box(1490, 705, 400, 115, "JIRA", "Ticket comment", ["data/jira_comments.json"])
box(1490, 840, 400, 115, "SLACK", "#qa-alerts", ["data/slack_messages.json"])

add("</svg>")
OUT.write_text("\n".join(parts) + "\n", encoding="utf-8")
print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
