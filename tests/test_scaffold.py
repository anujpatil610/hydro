"""Scaffold smoke tests — confirm the package tree imports cleanly.

Replaced/expanded by real tests in Stages 3 and 4.
"""

import importlib


def test_packages_import() -> None:
    for name in ("hal", "service", "service.api", "service.db"):
        assert importlib.import_module(name) is not None
