# File: services/telemetry.py
from __future__ import annotations
from typing import Optional
import time

try:
    from opentelemetry import trace, metrics
    from opentelemetry.trace.status import Status, StatusCode
    _tracer = trace.get_tracer("relay.mcp")
    _meter = metrics.get_meter("relay.mcp")
    _enabled = True
except Exception:  # OTEL not configured → safe no-op
    _tracer = None
    _meter = None
    _enabled = False

# Metrics (created once)
if _enabled and _meter:
    DEP_LATENCY = _meter.create_histogram(
        name="relay_connectivity_latency_ms",
        description="Dependency call latency (ms) by dependency and route",
        unit="ms",
    )
    DEP_ERRORS = _meter.create_counter(
        name="relay_connectivity_errors_total",
        description="Dependency errors by dependency and route",
        unit="1",
    )
    DEP_CALLS = _meter.create_counter(
        name="relay_connectivity_calls_total",
        description="Dependency calls by dependency and route",
        unit="1",
    )
    DEP_CIRCUIT = _meter.create_up_down_counter(
        name="relay_connectivity_circuit_state",
        description="Circuit state by dependency (-1 open, +1 closed)",
        unit="1",
    )
else:
    DEP_LATENCY = DEP_ERRORS = DEP_CALLS = DEP_CIRCUIT = None  # type: ignore

def tracer():
    return _tracer

def record_dep_call(dep: str, route: str, latency_ms: int, ok: bool, attrs: Optional[dict]=None):
    if not _enabled:
        return
    base = {"dep": dep, "route": route}
    if attrs:
        base.update(attrs)
    DEP_CALLS.add(1, base)
    DEP_LATENCY.record(latency_ms, base)
    if not ok:
        DEP_ERRORS.add(1, base)

def set_circuit_state(dep: str, is_closed: bool, route: str = "mcp"):
    if not _enabled:
        return
    DEP_CIRCUIT.add(+1 if is_closed else -1, {"dep": dep, "route": route})
