"""Thin CLI over ml/. Resolves created_at + git_commit and pins OMP_NUM_THREADS
at the boundary (HistGBT is bit-reproducible only at a fixed thread count), then
delegates to the importable, wall-clock-free library."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ml.config import CORPUS_CONFIG, CORPUS_ROOT, TrainConfig
from ml.data.corpus import ensure_corpus


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def _config_from_args(args: argparse.Namespace) -> TrainConfig:
    kw: dict[str, Any] = {}
    if args.n_splits is not None:
        kw["n_splits"] = args.n_splits
    if args.max_iter is not None:
        kw["max_iter"] = args.max_iter
    if args.windows:
        kw["windows"] = tuple(int(w) for w in args.windows.split(","))
    if getattr(args, "no_eval_extras", False):
        kw["run_eval_extras"] = False
    return TrainConfig(**kw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ml")
    sub = parser.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate-corpus", help="generate (or reuse) the training corpus")
    g.add_argument("--root", default=CORPUS_ROOT)
    g.add_argument("--config", default=CORPUS_CONFIG)
    g.add_argument("--regenerate", action="store_true")

    t = sub.add_parser("train", help="train estimators + save a bundle")
    t.add_argument("--corpus", default=CORPUS_ROOT)
    t.add_argument("--out", default="artifacts/latest")
    t.add_argument("--n-splits", type=int, default=None)
    t.add_argument("--max-iter", type=int, default=None)
    t.add_argument("--windows", default=None, help="comma list, e.g. 24,144,1008")
    t.add_argument("--threads", default="4", help="OMP_NUM_THREADS (determinism)")
    t.add_argument("--strict", action="store_true", help="non-zero exit if gate fails")
    t.add_argument("--no-eval-extras", action="store_true",
                   help="skip ablation/robustness/LOSO extras (faster; for CI)")

    e = sub.add_parser("evaluate", help="re-check the gate from a saved bundle")
    e.add_argument("--artifacts", required=True)

    args = parser.parse_args(argv)
    created_at = datetime.now(UTC).isoformat()

    if args.cmd == "generate-corpus":
        root = ensure_corpus(args.root, config_path=args.config,
                             regenerate=args.regenerate,
                             created_at=created_at, git_commit=_git_commit())
        print(f"corpus ready -> {root}")
        return 0

    if args.cmd == "train":
        os.environ["OMP_NUM_THREADS"] = args.threads
        from ml.models.train import train_all  # import after thread pin

        cfg = _config_from_args(args)
        report = train_all(args.corpus, config=cfg, out_dir=args.out,
                           created_at=created_at, git_commit=_git_commit(),
                           omp_num_threads=args.threads)
        verdict = "PASS" if report.gate.passed else "FAIL"
        print(f"gate: {verdict} -> {args.out}/report.md")
        return 1 if (args.strict and not report.gate.passed) else 0

    if args.cmd == "evaluate":
        from ml.models.train import load_bundle

        load_bundle(args.artifacts, strict=True)  # integrity + version check
        metrics = json.loads((Path(args.artifacts) / "metrics.json").read_text())
        gate = metrics["gate"]
        print(f"gate: {'PASS' if gate['passed'] else 'FAIL'} (bundle verified)")
        for k, v in gate["criteria"].items():
            print(f"  {k}: {'PASS' if v else 'FAIL'}")
        return 0
    return 2
