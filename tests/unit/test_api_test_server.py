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


@respx.mock
def test_run_api_test_returns_structured_error_on_transport_failure():
    respx.get("http://127.0.0.1:8000/tasks").mock(
        side_effect=httpx.ConnectError("boom")
    )
    result = run_api_test("GET", "/tasks", expected_status=200)
    assert result["passed"] is False
    assert result["method"] == "GET"
    assert result["path"] == "/tasks"
    assert result["expected_status"] == 200
    assert result["actual_status"] is None
    assert result["response_body"] is None
    assert "boom" in result["error"]
