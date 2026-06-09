from hal.base import Reading
from hal.factory import build_device_set
from service.profile.loader import load_profile


def test_sim_profile_builds_and_reads():
    profile = load_profile("profiles/bench-sim.yaml")
    ds = build_device_set(profile)
    # at least one sensor reads a finite value from the shared World
    sensors = [d for d in ds.devices.values() if hasattr(d, "read")]
    assert sensors
    r = sensors[0].read()
    assert isinstance(r, Reading)


def test_sim_pump_dose_moves_shared_world():
    profile = load_profile("profiles/bench-sim.yaml")
    ds = build_device_set(profile)
    pump = ds.devices["pump_resA"]
    ph_sensor = ds.devices["ph_resA"]
    # dosing nutrient must change the shared World the sensors read from
    before = ph_sensor.world.units["resA"].reservoir.n_mass_mg
    pump.dose_ml(50.0)
    after = ph_sensor.world.units["resA"].reservoir.n_mass_mg
    assert after > before
