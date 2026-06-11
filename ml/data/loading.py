"""Load a generated corpus into per-grow frames. The authoritative run list is
index.json (failed/partial runs excluded), so the loader never yields a grow the
factory could not complete."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class Grow:
    run_id: str
    scenario: str
    seed: int
    df: pd.DataFrame


def load_corpus(root: str | Path) -> list[Grow]:
    root = Path(root)
    index = json.loads((root / "index.json").read_text())
    grows: list[Grow] = []
    for r in index["runs"]:
        if r.get("status") != "ok":
            continue
        df = pd.read_parquet(root / r["dir"] / "data.parquet")
        grows.append(Grow(run_id=r["dir"], scenario=r["scenario"], seed=int(r["seed"]), df=df))
    return grows
