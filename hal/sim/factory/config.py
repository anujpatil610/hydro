"""Batch + run configuration. A BatchConfig is the source of truth; the CLI is a
thin YAML loader over it. A BatchConfig expands (seeds x scenarios) into N
RunConfigs (done in sweep.py)."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RunConfig(_Frozen):
    profile: str
    duration_days: float = Field(default=35, gt=0)
    sample_interval_s: float = Field(default=600.0, gt=0)
    integration_step_s: float = Field(default=300.0, gt=0)
    speed: float = Field(default=1.0, gt=0)  # informational for batch
    seed: int = 0
    scenario: str = "clean"
    # Seed-driven initial-condition variation so each seed is a distinct grow
    # (not just different sensor noise). 0 = identical trajectory across seeds.
    ic_jitter: float = Field(default=0.12, ge=0)


class BatchConfig(_Frozen):
    name: str
    base: RunConfig
    seeds: list[int] | dict[str, int] = Field(default_factory=lambda: [0])
    scenarios: list[str] = Field(default_factory=lambda: ["clean"])
    random_density: float = Field(default=3.0, ge=0)
    emit_csv: bool = False

    @property
    def seed_spec(self) -> dict[str, int] | None:
        return self.seeds if isinstance(self.seeds, dict) else None

    def seed_list(self) -> list[int | None]:
        """Explicit seeds as-is; count-form returns [None] (sweep spawns them)."""
        if isinstance(self.seeds, dict):
            return [None]
        return list(self.seeds)


def load_batch(path: str | Path) -> BatchConfig:
    data = yaml.safe_load(Path(path).read_text())
    return BatchConfig(**data)
