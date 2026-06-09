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
