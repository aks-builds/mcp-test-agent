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
    status matches expected_status. Returns a structured pass/fail result,
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
