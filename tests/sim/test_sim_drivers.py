from hal.base import PumpResult, Reading
from hal.sim.drivers import SimPump, SimSensor

from tests.sim.test_world import _world


def test_sim_sensor_returns_reading_from_world():
    w = _world()
    from hal.sim.noise import NoiseModel
    noise = NoiseModel(seed=7)
    s = SimSensor(metric="ph", kind="ph", unit="pH", reservoir_id="r1", world=w, noise=noise)
    r = s.read()
    assert isinstance(r, Reading)
    assert r.metric == "ph"
    assert 4.0 < r.value < 8.0
    assert r.ok is True


def test_sim_pump_dose_feeds_world():
    w = _world()
    from hal.sim.noise import NoiseModel
    noise = NoiseModel(seed=7)
    before = w.units["r1"].reservoir.n_mass_mg
    pump = SimPump(name="nutrient", role="dose-nutrient", reservoir_id="r1",
                   world=w, noise=noise, ml_per_min=50.0)
    res = pump.dose_ml(50.0)
    assert isinstance(res, PumpResult)
    assert res.estimated_ml == 50.0
    assert w.units["r1"].reservoir.n_mass_mg > before


def test_clogged_pump_delivers_less():
    from hal.sim.noise import Fault, NoiseModel
    w = _world()
    noise = NoiseModel(seed=7, faults=[Fault(kind="clog", metric="pump",
                                             start_s=0.0, duration_s=1e9, severity=1.0)])
    before = w.units["r1"].reservoir.n_mass_mg
    pump = SimPump(name="nutrient", role="dose-nutrient", reservoir_id="r1",
                   world=w, noise=noise, ml_per_min=50.0)
    pump.dose_ml(50.0)
    assert w.units["r1"].reservoir.n_mass_mg == before  # fully clogged -> no delivery


def test_noise_for_world_returns_shared_model():
    from hal.drivers.sim_drivers import noise_for_world
    from hal.factory import build_device_set
    from service.profile.loader import load_profile

    ds = build_device_set(load_profile("profiles/bench-sim.yaml"))
    nm = noise_for_world(ds.world)
    assert nm is not None
    sensor = next(s for s in ds.sensors() if hasattr(s, "noise"))
    assert nm is sensor.noise


def test_noise_for_world_unknown_world_is_none():
    from hal.drivers.sim_drivers import noise_for_world

    assert noise_for_world(object()) is None


def test_noise_seed_tracks_world_seed():
    from hal.drivers.sim_drivers import noise_for_world
    from hal.factory import build_device_set
    from service.profile.loader import load_profile

    ds = build_device_set(load_profile("profiles/bench-sim.yaml"), seed=42)
    assert noise_for_world(ds.world).seed == 42


def test_reset_noise_for_rebinds_seed_in_place():
    from hal.drivers.sim_drivers import noise_for_world, reset_noise_for
    from hal.factory import build_device_set
    from service.profile.loader import load_profile

    ds = build_device_set(load_profile("profiles/bench-sim.yaml"), seed=1)
    nm = noise_for_world(ds.world)
    ds.world.seed = 2
    reset_noise_for(ds.world)
    assert nm.seed == 2          # same NoiseModel object, reseeded (sensors stay wired)
    assert nm.faults == []
