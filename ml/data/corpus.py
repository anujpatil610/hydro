"""Generate the training corpus via B's factory, or reuse a complete one.

`ensure_corpus` is idempotent: a corpus whose index.json reports zero failures
and whose manifest matches the expected schema_version is reused untouched, so
training never silently runs on a partial or stale corpus."""

from __future__ import annotations

import json
from pathlib import Path

from hal.sim.factory.config import load_batch
from hal.sim.factory.sweep import run_batch

from ml.config import SCHEMA_VERSION


class CorpusError(RuntimeError):
    """The corpus on disk is incomplete, failed, or schema-mismatched."""


def _index_exists(root: Path) -> bool:
    return (root / "index.json").exists()


def _validate(root: Path) -> None:
    data = json.loads((root / "index.json").read_text())
    if data.get("failed", 0) != 0:
        raise CorpusError(f"corpus {root} has {data['failed']} failed run(s); regenerate")
    ok = [r for r in data["runs"] if r.get("status") == "ok"]
    if not ok:
        raise CorpusError(f"corpus {root} has no ok runs")
    manifest = json.loads((root / ok[0]["dir"] / "manifest.json").read_text())
    found = manifest.get("schema_version")
    if found != SCHEMA_VERSION:
        raise CorpusError(
            f"corpus schema_version {found!r} != expected {SCHEMA_VERSION!r}; regenerate"
        )


def ensure_corpus(
    root: str = "data/datasets/corpus",
    *,
    config_path: str = "runs/corpus.yaml",
    regenerate: bool = False,
    created_at: str,
    git_commit: str,
    workers: int | None = None,
) -> Path:
    """Return the corpus dir, generating it only when ``index.json`` is absent
    or ``regenerate=True``.

    If index.json already exists (even with failures), validate it and raise
    CorpusError rather than silently regenerating — the caller must pass
    ``regenerate=True`` to overwrite an existing corpus.

    `root` must equal `<out>/<batch.name>`; we derive out_root as its parent so
    run_batch writes the batch under the expected directory."""
    root_p = Path(root)
    if not regenerate and _index_exists(root_p):
        _validate(root_p)
        return root_p

    batch = load_batch(config_path)
    out_root = root_p.parent
    index = run_batch(batch, out_root=out_root, created_at=created_at,
                      git_commit=git_commit, workers=workers)
    produced = out_root / batch.name
    if produced != root_p:
        raise CorpusError(
            f"batch name {batch.name!r} writes {produced}, which does not match "
            f"requested root {root_p}; set the config's name to {root_p.name!r} or fix root"
        )
    if index["failed"]:
        raise CorpusError(
            f"corpus generation produced {index['failed']} failed run(s) -> {produced}"
        )
    _validate(produced)
    return produced
