"""API contract tests — mock mode, parametrized over bench + commercial.

Expectations come from the running profile (app.state), proving the contract
shape is fixed while counts scale with the profile.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _seed(client: TestClient, cycles: int = 1) -> None:
    for _ in range(cycles):
        client.app.state.poller.sample_once()


def _device_set(client: TestClient):
    return client.app.state.device_set


def test_health_reports_profile(client: TestClient) -> None:
    profile = client.app.state.profile
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["mode"] == "mock"
    assert body["uptime_s"] >= 0
    assert body["profile_id"] == profile.profile.id
    assert body["tier"] == profile.profile.tier
    assert body["device_count"] == len(profile.devices)
    assert body["validation_ok"] is True
    assert set(body["device_modes"]) == {d.id for d in profile.devices}


def test_topology_matches_profile(client: TestClient) -> None:
    profile = client.app.state.profile
    r = client.get("/topology")
    assert r.status_code == 200
    body = r.json()
    assert body["profile"]["id"] == profile.profile.id
    assert {z["id"] for z in body["zones"]} == {z.id for z in profile.zones}
    assert {res["id"] for res in body["reservoirs"]} == {r.id for r in profile.reservoirs}
    assert {d["id"] for d in body["devices"]} == {d.id for d in profile.devices}
    # Every device carries a resolved mode + display unit.
    for d in body["devices"]:
        assert d["mode"] in {"mock", "real"}


def test_sensors_empty_before_seeding(client: TestClient) -> None:
    r = client.get("/sensors")
    assert r.status_code == 200
    assert r.json() == []


def test_sensors_latest_one_row_per_sensor(client: TestClient) -> None:
    _seed(client, cycles=2)
    r = client.get("/sensors")
    assert r.status_code == 200
    rows = r.json()
    sensor_ids = {d.id for d in client.app.state.profile.devices if d.kind in
                  {"ph", "tds", "ec", "temp", "rh", "level", "co2", "par"}}
    assert {row["device_id"] for row in rows} == sensor_ids
    for row in rows:
        assert {"device_id", "kind", "metric", "value", "unit", "ok", "note",
                "timestamp", "zone_id", "reservoir_id"} <= row.keys()


def test_sensors_filter_by_zone_and_kind(client: TestClient) -> None:
    _seed(client)
    # Pick a real zone from the profile.
    zone = client.app.state.profile.zones[0].id
    r = client.get("/sensors", params={"zone": zone})
    assert r.status_code == 200
    assert all(row["zone_id"] == zone for row in r.json())

    r = client.get("/sensors", params={"kind": "ph"})
    assert all(row["kind"] == "ph" for row in r.json())
    assert len(r.json()) == len(_device_set(client).by_kind("ph"))


def test_history_window_and_device_filter(client: TestClient) -> None:
    _seed(client, cycles=3)
    n_sensors = len(_device_set(client).sensors())
    r = client.get("/sensors/history", params={"hours": 24})
    assert r.status_code == 200
    assert len(r.json()) == 3 * n_sensors

    # filter to a single device
    a_device = next(d.id for d in client.app.state.profile.devices
                    if d.kind in {"ph", "tds", "temp"})
    r = client.get("/sensors/history", params={"hours": 24, "device_id": a_device})
    assert len(r.json()) == 3
    assert all(row["device_id"] == a_device for row in r.json())

    assert client.get("/sensors/history", params={"hours": 0}).status_code == 422
    assert client.get("/sensors/history", params={"hours": 999}).status_code == 422


def test_actuator_test_by_device_id(client: TestClient) -> None:
    pump_id = next(d.id for d in client.app.state.profile.devices if d.kind == "pump")
    r = client.post(f"/actuators/{pump_id}/test", json={"ml": 10})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["estimated_ml"] == 10.0  # dose-by-ml is flow-rate independent
    assert body["ran_for_ms"] > 0


def test_actuator_test_unknown_device_404(client: TestClient) -> None:
    assert client.post("/actuators/nope/test", json={"ml": 1}).status_code == 404


def test_actuator_test_non_pump_422(client: TestClient) -> None:
    sensor_id = next(d.id for d in client.app.state.profile.devices if d.kind != "pump")
    assert client.post(f"/actuators/{sensor_id}/test", json={"ml": 1}).status_code == 422


def test_actuator_validation_errors(client: TestClient) -> None:
    pump_id = next(d.id for d in client.app.state.profile.devices if d.kind == "pump")
    assert client.post(f"/actuators/{pump_id}/test", json={}).status_code == 422
    assert client.post(
        f"/actuators/{pump_id}/test", json={"ml": 1, "duration_ms": 1}
    ).status_code == 422
    assert client.post(f"/actuators/{pump_id}/test", json={"duration_ms": 0}).status_code == 422


def test_legacy_pump_alias(client: TestClient) -> None:
    n_pumps = len(_device_set(client).by_kind("pump"))
    r = client.post("/actuators/pump/test", json={"ml": 5})
    if n_pumps == 1:
        assert r.status_code == 200
        assert r.json()["estimated_ml"] == 5.0
    else:
        # Ambiguous with multiple pumps -> 409 directing to the per-device route.
        assert r.status_code == 409
