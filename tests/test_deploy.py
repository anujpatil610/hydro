"""Deploy-phase integration tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
ENV_EXAMPLE = REPO_ROOT / "deploy" / ".env.example"
INSTALL_SH = REPO_ROOT / "deploy" / "install.sh"
HYDRO_SERVICE = REPO_ROOT / "deploy" / "hydro.service"

REQUIRED_ENV_KEYS = {
    "HYDRO_MODE",
    "HYDRO_HOST",
    "HYDRO_PORT",
    "HYDRO_DB_PATH",
    "HYDRO_POLL_SECONDS",
    "HYDRO_RETENTION_HOURS",
    "HYDRO_PUMP_ML_PER_MIN",
    "HYDRO_CALIBRATION_PATH",
}


def test_env_example_has_all_required_keys():
    content = ENV_EXAMPLE.read_text()
    keys = set()
    for line in content.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            keys.add(line.split("=", 1)[0])
    missing = REQUIRED_ENV_KEYS - keys
    assert not missing, f"Missing keys in .env.example: {missing}"


def test_install_sh_syntax():
    result = subprocess.run(
        ["sh", "-n", str(INSTALL_SH)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"sh -n failed: {result.stderr}"
    assert result.stderr == "", f"Unexpected stderr: {result.stderr}"


def test_install_sh_has_fail_fast_and_mode_guard():
    content = INSTALL_SH.read_text()
    assert "set -eu" in content, "install.sh must have 'set -eu'"
    assert '"mock"' in content or "'mock'" in content, "install.sh must validate 'mock' mode"
    assert '"real"' in content or "'real'" in content, "install.sh must validate 'real' mode"


def test_hydro_service_required_directives():
    content = HYDRO_SERVICE.read_text()
    required = [
        "ExecStart=",
        "EnvironmentFile=",
        "Restart=",
        "StandardOutput=journal",
        "WantedBy=default.target",
    ]
    for directive in required:
        assert directive in content, f"Missing directive in hydro.service: {directive}"


def test_health_endpoint_mock_mode(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["mode"] == "mock"

    client.app.state.poller.sample_once()
    resp2 = client.get("/sensors")
    assert resp2.status_code == 200
    data = resp2.json()
    assert isinstance(data, list) and len(data) > 0, "Expected non-empty sensor list"
    for item in data:
        assert "metric" in item, f"Missing 'metric' key in {item}"
        assert "value" in item, f"Missing 'value' key in {item}"
        assert "unit" in item, f"Missing 'unit' key in {item}"
