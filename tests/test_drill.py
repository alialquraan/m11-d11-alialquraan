"""Self-tests for the toy-service instrumentation."""

import re
from fastapi.testclient import TestClient

from app import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# 1. Metrics endpoint reachable after traffic
# ---------------------------------------------------------------------------

def test_metrics_endpoint_returns_200_after_traffic():

    for _ in range(3):
        client.post("/echo", json={"message": "hello"})

    for _ in range(2):
        client.get("/sum?a=1&b=2")

    response = client.get("/metrics")

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# 2. Metrics contain required metric families
# ---------------------------------------------------------------------------

def test_metrics_body_contains_three_metric_families():

    response = client.get("/metrics")
    body = response.text

    assert "requests_total" in body
    assert "request_latency_seconds" in body
    assert "inflight_requests" in body


# ---------------------------------------------------------------------------
# 3. requests_total counter correctness
# ---------------------------------------------------------------------------

def test_echo_counter_has_expected_value():

    for _ in range(3):
        client.post("/echo", json={"message": "hello"})

    body = client.get("/metrics").text

    pattern = r'requests_total\{path="/echo",status="200"\}\s+(\d+)'

    match = re.search(pattern, body)

    assert match is not None

    value = int(match.group(1))

    assert value >= 3


# ---------------------------------------------------------------------------
# 4. Request ID header validation
# ---------------------------------------------------------------------------

def test_x_request_id_header_set_on_every_non_metrics_response():

    r1 = client.post("/echo", json={"message": "hello"})
    r2 = client.get("/sum?a=1&b=2")

    assert "X-Request-ID" in r1.headers
    assert "X-Request-ID" in r2.headers

    assert r1.headers["X-Request-ID"] != ""
    assert r2.headers["X-Request-ID"] != ""