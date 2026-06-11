import json

from ml.cli import main


def test_generate_corpus_then_train_then_evaluate(tmp_path, tiny_corpus):
    art = tmp_path / "artifacts" / "run"
    # train against the prebuilt tiny corpus (ensure_corpus reuses it)
    rc = main([
        "train", "--corpus", str(tiny_corpus), "--out", str(art),
        "--n-splits", "2", "--max-iter", "15", "--windows", "4,8",
    ])
    assert rc in (0, 1)  # 0 pass / 1 gate-fail; both are valid runs
    assert (art / "manifest.json").exists()

    rc2 = main(["evaluate", "--artifacts", str(art)])
    assert rc2 == 0


def test_train_sets_and_records_omp_threads(tmp_path, tiny_corpus, monkeypatch):
    art = tmp_path / "a"
    main(["train", "--corpus", str(tiny_corpus), "--out", str(art),
          "--n-splits", "2", "--max-iter", "15", "--windows", "4,8", "--threads", "1"])
    man = json.loads((art / "manifest.json").read_text())
    assert man["omp_num_threads"] == "1"
