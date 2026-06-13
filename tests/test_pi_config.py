"""Pi config hardening tests."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
HYDRO_SERVICE = REPO_ROOT / "deploy" / "hydro.service"
HARDENING_SH = REPO_ROOT / "deploy" / "hardening.sh"
CLEANUP_SH = REPO_ROOT / "deploy" / "cleanup.sh"

# Set HYDRO_PI_HOST=hydropi@172.20.6.122 to run live Pi connectivity tests.
_PI_HOST = os.environ.get("HYDRO_PI_HOST", "")

# Packages that must be absent after cleanup.sh runs.
BLOAT_PACKAGES = [
    "vlc",
    "thonny",
    "xserver-xorg",
    "lightdm",
    "cups-daemon",
    "bluez",
    "openbox",
    "pcmanfm",
    "gdb",
    "nfs-common",
]


def test_service_has_no_new_privileges():
    content = HYDRO_SERVICE.read_text()
    assert "NoNewPrivileges=yes" in content


def test_service_has_private_tmp():
    content = HYDRO_SERVICE.read_text()
    assert "PrivateTmp=yes" in content


def test_service_restart_policy_is_always():
    # Always-on living twin: restart on clean exits too (not just failures), so
    # the 24/7 sim survives reboots/redeploys. StartLimitBurst caps crash-looping.
    content = HYDRO_SERVICE.read_text()
    assert "Restart=always" in content
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
    assert "chmod" in content
    lines = content.splitlines()
    # .env must be locked to owner-read-only (600), whether via a literal
    # `chmod 600 .env` or a path:mode table entry like `.env:600`.
    assert any(".env" in line and "600" in line for line in lines), (
        "Expected .env to be assigned mode 600 in hardening.sh"
    )


def test_cleanup_sh_syntax():
    result = subprocess.run(
        ["sh", "-n", str(CLEANUP_SH)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"sh -n failed: {result.stderr}"


def test_cleanup_sh_targets_all_bloat_categories():
    """cleanup.sh must reference every known bloat package."""
    content = CLEANUP_SH.read_text()
    missing = [pkg for pkg in BLOAT_PACKAGES if pkg not in content]
    assert not missing, f"cleanup.sh does not mention these bloat packages: {missing}"


@pytest.mark.skipif(not _PI_HOST, reason="Set HYDRO_PI_HOST=user@host to run live Pi tests")
def test_bloat_packages_absent_on_pi():
    """SSH into the Pi and confirm every bloat package is deinstalled."""
    query = " ".join(f"'{p}'" for p in BLOAT_PACKAGES)
    result = subprocess.run(
        [
            "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
            _PI_HOST,
            f"for pkg in {query}; do "
            f"dpkg-query -W -f='${{Package}} ${{Status}}\\n' \"$pkg\" 2>/dev/null || true; "
            f"done",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"SSH failed: {result.stderr}"
    still_installed = [
        line.split()[0]
        for line in result.stdout.splitlines()
        if "install ok installed" in line
    ]
    assert not still_installed, (
        f"Bloat packages still installed on Pi — run sudo ./deploy/cleanup.sh: {still_installed}"
    )
