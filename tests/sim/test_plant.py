from hal.sim.crop import load_crop
from hal.sim.plant import PlantModel


def _plant():
    return PlantModel(crop=load_crop("lettuce"), biomass_g=0.05, days_elapsed=0.0,
                      health=1.0)


def test_stage_progresses_with_days():
    p = _plant()
    assert p.stage() == "germination"
    p.days_elapsed = 12.0
    assert p.stage() == "vegetative"
    p.days_elapsed = 40.0
    assert p.stage() == "mature"


def test_growth_rate_positive_when_healthy():
    p = _plant()
    assert p.growth_rate_per_day() > 0


def test_growth_rate_scales_with_health():
    p = _plant()
    full = p.growth_rate_per_day()
    p.health = 0.5
    assert p.growth_rate_per_day() < full


def test_nutrient_uptake_saturates_and_respects_cmin():
    p = _plant()
    p.biomass_g = 2.0
    high = p.uptake_mg_per_day(conc={"n": 200.0, "p": 40.0, "k": 160.0})
    low = p.uptake_mg_per_day(conc={"n": 5.0, "p": 1.0, "k": 4.0})
    assert high["n"] > low["n"] > 0
    # below cmin -> no net uptake
    none = p.uptake_mg_per_day(conc={"n": 0.5, "p": 0.1, "k": 0.4})
    assert none["n"] == 0.0


def test_stress_raises_when_ph_far_from_optimal():
    p = _plant()
    healthy = p.stress(observed={"ph": 5.8, "ec": 1.5, "temp": 21.0})
    stressed = p.stress(observed={"ph": 8.5, "ec": 1.5, "temp": 21.0})
    assert stressed > healthy
