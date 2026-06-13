from sqlmodel import Session

from hal.sim.build import build_world
from service.db.session import (
    clear_twin_samples, init_db, load_checkpoint, make_engine, save_checkpoint,
)
from service.db.models import TwinSample, naive_utc
from service.profile.loader import load_profile


def _world():
    return build_world(load_profile("profiles/bench-sim.yaml"), seed=9, ic_jitter=0.1)


def test_load_returns_none_when_empty():
    engine = make_engine(":memory:")
    init_db(engine)
    with Session(engine) as s:
        assert load_checkpoint(s) is None


def test_save_then_load_round_trip():
    engine = make_engine(":memory:")
    init_db(engine)
    world = _world()
    for _ in range(3):
        world.step()
    expected = world.to_state()
    with Session(engine) as s:
        save_checkpoint(s, expected)
        s.commit()
    with Session(engine) as s:
        loaded = load_checkpoint(s)
    assert loaded.seed == 9
    assert loaded.grow_id == expected.grow_id
    assert loaded.sim_time_s == expected.sim_time_s
    assert loaded.reservoirs == expected.reservoirs


def test_save_is_upsert_one_row_per_reservoir():
    engine = make_engine(":memory:")
    init_db(engine)
    world = _world()
    with Session(engine) as s:
        save_checkpoint(s, world.to_state())
        world.step()
        save_checkpoint(s, world.to_state())
        s.commit()
    from sqlmodel import select
    from service.db.models import TwinCheckpoint
    with Session(engine) as s:
        rows = s.exec(select(TwinCheckpoint)).all()
    assert len(rows) == len(world.units)  # upsert, not append


def test_clear_twin_samples_removes_all():
    engine = make_engine(":memory:")
    init_db(engine)
    with Session(engine) as s:
        s.add(TwinSample(
            timestamp=naive_utc(), reservoir_id="resA", stage="germination",
            biomass_g=0.1, health=1.0, ph_true=5.8, ec_true=1.4, temp_true=21.0,
            volume_l=20.0, n_mg_l=100.0, p_mg_l=20.0, k_mg_l=80.0,
        ))
        s.commit()
        assert clear_twin_samples(s) == 1
        s.commit()
