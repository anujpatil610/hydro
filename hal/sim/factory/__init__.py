"""Headless batch data factory: drives the digital twin (Sub-project A) to
generate labeled synthetic datasets. See
docs/superpowers/specs/2026-06-09-sim-data-factory-design.md."""

from hal.sim.factory.config import BatchConfig, RunConfig, load_batch
from hal.sim.factory.runner import run_one
from hal.sim.factory.sweep import expand, run_batch

__all__ = ["BatchConfig", "RunConfig", "load_batch", "run_one", "expand", "run_batch"]
