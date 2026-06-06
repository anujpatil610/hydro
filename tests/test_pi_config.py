"""Pi config hardening tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
HYDRO_SERVICE = REPO_ROOT / "deploy" / "hydro.service"
HARDENING_SH = REPO_ROOT / "deploy" / "hardening.sh"


def test_service_has_no_new_privileges():
    content = HYDRO_SERVICE.read_text()
    assert "NoNewPrivileges=yes" in content


def test_service_has_private_tmp():
    content = HYDRO_SERVICE.read_text()
    assert "PrivateTmp=yes" in content


def test_service_restart_policy_is_on_failure():
    content = HYDRO_SERVICE.read_text()
    assert "Restart=on-failure" in content
    assert "StartLimitBurst=" in content


def test_hardening_sh_syntax():
    result = subprocess.run(
        ["sh", "-n", str(HARDENING_SH)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"sh -n failed: {result.stderr}"


def test_hardening_sh_sets_env_permissions():
    content = HARDENING_SH.read_text()
    assert "chmod 600" in content
    lines = content.splitlines()
    assert any("chmod 600" in line and ".env" in line for line in lines), (
        "Expected a line containing both 'chmod 600' and '.env'"
    )
