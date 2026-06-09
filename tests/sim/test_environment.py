from hal.sim.environment import Zone


def _zone():
    return Zone(
        zone_id="z1",
        air_temp_day_c=24.0, air_temp_night_c=19.0,
        humidity_pct=65.0, photoperiod_h=16.0, ppfd=250.0,
        light_load_c=1.5, ripple_amp_c=0.3,
    )


def test_light_on_within_photoperiod():
    z = _zone()
    assert z.light_on(sim_time_s=4 * 3600) is True       # hour 4 of 16h-on
    assert z.light_on(sim_time_s=20 * 3600) is False      # hour 20, dark


def test_air_temp_warmer_under_light():
    z = _zone()
    day = z.air_temp_c(sim_time_s=4 * 3600, disturbance_c=0.0)
    night = z.air_temp_c(sim_time_s=20 * 3600, disturbance_c=0.0)
    assert day > night
    # within ripple of (setpoint + light load) by day
    assert abs(day - (24.0 + 1.5)) <= 0.3 + 1e-9


def test_disturbance_adds_to_temp():
    z = _zone()
    base = z.air_temp_c(sim_time_s=4 * 3600, disturbance_c=0.0)
    bumped = z.air_temp_c(sim_time_s=4 * 3600, disturbance_c=5.0)
    assert bumped == base + 5.0
