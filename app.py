"""Toy FastAPI service for the Module 11 Core Skills Drill.

Two endpoints (POST /echo, GET /sum) on an in-memory app.
"""

import contextvars
import json
import logging
import time
import uuid

from fastapi import FastAPI
from pydantic import BaseModel
from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    make_asgi_app,
)
from starlette.middleware.base import BaseHTTPMiddleware


# ---------------------------------------------------------------------------
# Prometheus Metrics
# ---------------------------------------------------------------------------

requests_total = Counter(
    "requests_total",
    "Total HTTP requests",
    ["path", "status"],
)

request_latency_seconds = Histogram(
    "request_latency_seconds",
    "Request latency in seconds",
    ["path"],
    buckets=[
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1,
        2.5,
        5,
        10,
    ],
)

inflight_requests = Gauge(
    "inflight_requests",
    "In-flight requests",
)


# ---------------------------------------------------------------------------
# Context Variable
# ---------------------------------------------------------------------------

request_id_var = contextvars.ContextVar(
    "request_id",
    default="",
)


# ---------------------------------------------------------------------------
# Middlewares
# ---------------------------------------------------------------------------

class RequestIdMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request, call_next):
        request_id = uuid.uuid4().hex

        request_id_var.set(request_id)

        response = await call_next(request)

        response.headers["X-Request-ID"] = request_id

        return response


class StructuredLoggingMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request, call_next):
        start = time.perf_counter()

        response = await call_next(request)

        latency_ms = (time.perf_counter() - start) * 1000

        log = {
            "ts": time.time(),
            "level": "INFO",
            "request_id": request_id_var.get(),
            "path": request.url.path,
            "status": response.status_code,
            "latency_ms": latency_ms,
        }

        logging.getLogger("app").info(json.dumps(log))

        return response


class MetricsMiddleware:

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):

        # استثناء الطلبات التي ليست HTTP أو الطلبات الموجهة لمسار المقاييس
        if scope["type"] != "http" or scope.get("path") == "/metrics":
            await self.app(scope, receive, send)
            return

        inflight_requests.inc()

        start = time.perf_counter()

        status_code = None

        async def send_wrapper(message):

            nonlocal status_code

            if message["type"] == "http.response.start":
                status_code = message["status"]

            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)

        finally:
            inflight_requests.dec()

            elapsed = time.perf_counter() - start

            if status_code is not None:

                requests_total.labels(
                    path=scope["path"],
                    status=str(status_code),
                ).inc()

                request_latency_seconds.labels(
                    path=scope["path"],
                ).observe(elapsed)


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(title="M11 Drill — Toy FastAPI Service")


# Order matters:
# Metrics -> Logging -> RequestId
# (Last added middleware runs first)

app.add_middleware(RequestIdMiddleware)
app.add_middleware(StructuredLoggingMiddleware)
app.add_middleware(MetricsMiddleware)


# ---------------------------------------------------------------------------
# Prometheus Endpoint
# ---------------------------------------------------------------------------

app.mount("/metrics", make_asgi_app())


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class EchoRequest(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/echo")
def echo(req: EchoRequest):
    return {"echo": req.message}


@app.get("/sum")
def sum_endpoint(a: int = 0, b: int = 0):
    return {"sum": a + b}