"""Shared fixtures for ml tests. `tiny_corpus` generates a real but minimal
corpus once per test session via B's factory, so feature/split/train tests run
against genuine parquet without the cost of the full 300-grow corpus."""

from __future__ import annotations

from pathlib import Path

import pytest
from hal.sim.factory.config import BatchConfig, RunConfig
from hal.sim.factory.sweep import run_batch


@pytest.fixture(scope="session")
def tiny_corpus(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 2-seed x 2-scenario x 2-day corpus (4 grows). Returns the dataset dir
    (contains index.json + run dirs with data.parquet)."""
    out_root = tmp_path_factory.mktemp("datasets")
    batch = BatchConfig(
        name="tiny",
        base=RunConfig(
            profile="profiles/bench-sim.yaml",
            duration_days=2,
            sample_interval_s=3600.0,  # hourly -> ~48 rows/grow, fast
            ic_jitter=0.12,
        ),
        seeds=[1, 2],
        scenarios=["clean", "chaos"],
    )
    run_batch(batch, out_root=out_root, created_at="t", git_commit="c", workers=1)
    return out_root / "tiny"
