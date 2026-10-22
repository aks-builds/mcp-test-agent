import os
from typing import Any

import httpx
from fastmcp import FastMCP

APP_URL = os.environ.get("APP_URL", "http://127.0.0.1:8000")

mcp = FastMCP("api-test")


@mcp.tool()
def run_api_test(
    method: str,
    path: str,
    body: dict | None = None,
    expected_status: int = 200,
) -> dict:
    """Execute an HTTP call against the app under test and assert the response
    status matches expected_status. Returns a structured pass/fail result,
    never raises for a failed assertion or a transport-level error; a
    transport error (e.g. the app is unreachable) comes back as a
    failed result with an added error key."""
    url = f"{APP_URL}{path}"
    try:
        response = httpx.request(method.upper(), url, json=body, timeout=5.0)
    except httpx.HTTPError as exc:
        return {
            "passed": False,
            "method": method.upper(),
            "path": path,
            "expected_status": expected_status,
            "actual_status": None,
            "response_body": None,
            "error": str(exc),
        }
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
