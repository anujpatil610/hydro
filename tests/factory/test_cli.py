import json

from hal.sim.factory.cli import main


def test_cli_run_generates_dataset(tmp_path, capsys):
    batch = tmp_path / "b.yaml"
    batch.write_text(
        "name: cli_demo\n"
        "base: {profile: profiles/bench-sim.yaml, duration_days: 1, sample_interval_s: 3600}\n"
        "seeds: [1]\n"
        "scenarios: [clean]\n"
    )
    code = main(["run", str(batch), "--out", str(tmp_path), "--workers", "1"])
    assert code == 0
    index = json.loads((tmp_path / "cli_demo" / "index.json").read_text())
    assert index["run_count"] == 1
    assert "rows" in capsys.readouterr().out.lower()


def test_cli_inspect_prints_summary(tmp_path, capsys):
    batch = tmp_path / "b.yaml"
    batch.write_text(
        "name: insp\n"
        "base: {profile: profiles/bench-sim.yaml, duration_days: 1, sample_interval_s: 3600}\n"
        "seeds: [1]\nscenarios: [clean]\n"
    )
    main(["run", str(batch), "--out", str(tmp_path), "--workers", "1"])
    capsys.readouterr()
    code = main(["inspect", str(tmp_path / "insp")])
    assert code == 0
    assert "insp" in capsys.readouterr().out
