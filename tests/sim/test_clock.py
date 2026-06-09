from hal.sim.clock import SimClock


def test_advance_accumulates_sim_seconds():
    clk = SimClock(integration_step_s=60.0, sample_interval_s=600.0, speed=1.0)
    clk.advance(600.0)
    assert clk.sim_time_s == 600.0


def test_steps_for_yields_integration_substeps():
    clk = SimClock(integration_step_s=60.0, sample_interval_s=600.0, speed=1.0)
    # one sample interval = 600s / 60s step = 10 substeps
    spans = list(clk.steps_for(600.0))
    assert len(spans) == 10
    assert spans[0] == (0.0, 60.0)
    assert spans[-1] == (540.0, 600.0)


def test_uneven_interval_has_short_final_step():
    clk = SimClock(integration_step_s=60.0, sample_interval_s=600.0, speed=1.0)
    spans = list(clk.steps_for(90.0))
    assert spans == [(0.0, 60.0), (60.0, 90.0)]
