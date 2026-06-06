"""API contract tests — mock mode, TestClient against a temp SQLite DB."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _seed(client: TestClient, cycles: int = 1) -> None:
    for _ in range(cycles):
        client.app.state.poller.sample_once()


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["mode"] == "mock"
    assert body["uptime_s"] >= 0


def test_sensors_empty_before_seeding(client: TestClient) -> None:
    r = client.get("/sensors")
    assert r.status_code == 200
    assert r.json() == []


def test_sensors_latest(client: TestClient) -> None:
    _seed(client, cycles=2)
    r = client.get("/sensors")
    assert r.status_code == 200
    metrics = {row["metric"] for row in r.json()}
    assert metrics == {"ph", "tds", "temp"}
    for row in r.json():
        assert {"metric", "value", "unit", "ok", "note", "timestamp"} <= row.keys()


def test_history_returns_window_and_validates_range(client: TestClient) -> None:
    _seed(client, cycles=3)
    r = client.get("/sensors/history", params={"hours": 24})
    assert r.status_code == 200
    assert len(r.json()) == 9  # 3 cycles x 3 metrics
    # out-of-range hours rejected
    assert client.get("/sensors/history", params={"hours": 0}).status_code == 422
    assert client.get("/sensors/history", params={"hours": 999}).status_code == 422


def test_pump_test_by_ml(client: TestClient) -> None:
    r = client.post("/actuators/pump/test", json={"ml": 10})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["ran_for_ms"] == 10_000  # 10 mL at 60 mL/min
    assert body["estimated_ml"] == 10.0


def test_pump_test_by_duration(client: TestClient) -> None:
    r = client.post("/actuators/pump/test", json={"duration_ms": 3000})
    assert r.status_code == 200
    assert r.json()["estimated_ml"] == 3.0  # 3s at 1 mL/sec


def test_pump_test_requires_exactly_one_arg(client: TestClient) -> None:
    assert client.post("/actuators/pump/test", json={}).status_code == 422
    assert (
        client.post("/actuators/pump/test", json={"ml": 1, "duration_ms": 1}).status_code == 422
    )


def test_pump_test_rejects_nonpositive(client: TestClient) -> None:
    assert client.post("/actuators/pump/test", json={"duration_ms": 0}).status_code == 422
