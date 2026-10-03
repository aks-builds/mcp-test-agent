import httpx
import respx

from servers.ticket_spec.server import get_ticket, get_openapi_spec


def test_get_ticket_returns_known_ticket():
    result = get_ticket("NASH-101")
    assert result["id"] == "NASH-101"
    assert "Given" in result["description"]
    assert "#add-task-btn" in result["description"]


def test_get_ticket_unknown_id_returns_error():
    result = get_ticket("NASH-999")
    assert result == {"error": "ticket NASH-999 not found"}


@respx.mock
def test_get_openapi_spec_fetches_from_demo_app():
    respx.get("http://127.0.0.1:8000/openapi.json").mock(
        return_value=httpx.Response(200, json={"openapi": "3.1.0", "paths": {}})
    )
    result = get_openapi_spec()
    assert result["openapi"] == "3.1.0"


@respx.mock
def test_get_openapi_spec_returns_error_on_transport_failure():
    respx.get("http://127.0.0.1:8000/openapi.json").mock(
        side_effect=httpx.ConnectError("boom")
    )
    result = get_openapi_spec()
    assert "error" in result
    assert "boom" in result["error"]
