"""Driver registry: registration, (kind, driver, mode) resolution, errors."""

from __future__ import annotations

import pytest


def test_register_and_resolve_roundtrip() -> None:
    from hal.registry import Registry

    reg = Registry()

    @reg.register("ph", "fake", "mock")
    def _build(*, binding, spec, ctx):  # noqa: ANN001, ARG001
        return "ph-mock-instance"

    builder = reg.resolve("ph", "fake", "mock")
    assert builder(binding=None, spec=None, ctx=None) == "ph-mock-instance"


def test_resolve_unknown_driver_raises_with_listing() -> None:
    from hal.registry import Registry
    from service.profile.schema import ProfileError

    reg = Registry()

    @reg.register("ph", "ads1115", "mock")
    def _build(*, binding, spec, ctx):  # noqa: ANN001, ARG001
        return object()

    with pytest.raises(ProfileError) as exc:
        reg.resolve("ph", "serial-ph", "real")
    msg = str(exc.value)
    assert "ph" in msg and "serial-ph" in msg
    # The error lists what IS registered, to guide the fix.
    assert "ads1115" in msg


def test_default_registry_has_all_profile_kinds_in_mock() -> None:
    """Every kind used by the shipped profiles resolves in mock mode."""
    import hal.drivers  # noqa: F401  (populates the default registry)
    from hal.registry import REGISTRY
    from service.profile.loader import load_profile

    for name in ("bench", "commercial"):
        profile = load_profile(f"profiles/{name}.yaml")
        for dev in profile.devices:
            # Should not raise: a mock builder exists for every kind/driver used.
            REGISTRY.resolve(dev.kind, dev.driver, "mock")
