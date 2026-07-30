"""CLI train/eval subcommands and classifier selection wiring (tasks 6.1-6.3)."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from click.testing import CliRunner

from atlas_conductor import cli as cli_mod
from atlas_conductor.classifier import RuleClassifier
from atlas_conductor.classifier.learned import LearnedClassifier
from atlas_conductor.config import JobConfig
from atlas_conductor.contracts import Geometry, RequestedOutput
from atlas_conductor.dispatch import FakeAdapter, Injection
from atlas_conductor.run import make_classifier, run_job
from atlas_conductor.telemetry import InMemoryTelemetrySink, JsonlTelemetrySink

GEO = Geometry(patch_size=256, target_mag=20)


def _cohort(tmp_path: Path, modes: dict[str, str]) -> Path:
    cohort = tmp_path / "cohort"
    cohort.mkdir(parents=True, exist_ok=True)
    for stem in modes:
        (cohort / f"{stem}.svs").write_bytes(b"fake-wsi")
    return cohort


def _config(cohort: Path, out: Path, **overrides) -> JobConfig:
    base = JobConfig(
        input_dir=cohort,
        output_dir=out,
        requested_output=RequestedOutput.FEATURES,
        geometry=GEO,
        encoders=("resnet50",),
    )
    return replace(base, **overrides) if overrides else base


def _injections(modes: dict[str, str]) -> dict[str, Injection]:
    # oom resolves on retry; others persist to a terminal action — both yield recovery rows.
    return {
        stem: Injection(mode, fail_until_attempt=1 if mode == "oom" else 1_000_000, label=label)
        for stem, (mode, label) in {
            s: (m, "cuda-oom" if m == "oom" else m) for s, m in modes.items()
        }.items()
    }


def _write_recovery_telemetry(tmp_path: Path) -> Path:
    """Run a mixed cohort with injected failures to a JSONL telemetry dir; return that dir."""
    modes = {f"oom{i}": "oom" for i in range(8)}
    modes.update({f"nan{i}": "nan" for i in range(8)})
    cohort = _cohort(tmp_path, modes)
    out = tmp_path / "out"
    telemetry_dir = out / "telemetry"
    run_job(
        _config(cohort, out),
        JsonlTelemetrySink(telemetry_dir),
        adapter=FakeAdapter(injections=_injections(modes)),
    )
    return telemetry_dir


# -- CLI subcommands (6.1) -------------------------------------------------------


def test_train_classifier_writes_a_model(tmp_path: Path) -> None:
    telemetry_dir = _write_recovery_telemetry(tmp_path)
    model_path = tmp_path / "model.json"
    result = CliRunner().invoke(
        cli_mod.cli, ["train-classifier", str(telemetry_dir), "-o", str(model_path)]
    )
    assert result.exit_code == 0, result.output
    assert model_path.is_file()
    data = json.loads(model_path.read_text(encoding="utf-8"))
    assert data["feature_version"] == "lrc-1"
    assert "weights" in data and "bias" in data


def test_eval_classifier_reports_accuracy_and_safety(tmp_path: Path) -> None:
    telemetry_dir = _write_recovery_telemetry(tmp_path)
    model_path = tmp_path / "model.json"
    CliRunner().invoke(cli_mod.cli, ["train-classifier", str(telemetry_dir), "-o", str(model_path)])

    result = CliRunner().invoke(
        cli_mod.cli, ["eval-classifier", str(telemetry_dir), "--model", str(model_path)]
    )
    assert result.exit_code == 0, result.output
    assert "accuracy" in result.output
    assert "safety_metric" in result.output


# -- make_classifier factory + fallback (6.2) -----------------------------------


def test_make_classifier_defaults_to_rule() -> None:
    config = _config(Path("c"), Path("o"))
    assert isinstance(make_classifier(config), RuleClassifier)


def test_make_classifier_learned_loads_a_model(tmp_path: Path) -> None:
    telemetry_dir = _write_recovery_telemetry(tmp_path)
    model_path = tmp_path / "model.json"
    CliRunner().invoke(cli_mod.cli, ["train-classifier", str(telemetry_dir), "-o", str(model_path)])
    config = _config(
        tmp_path / "c",
        tmp_path / "o",
        classifier_backend="learned",
        classifier_model_path=str(model_path),
    )
    assert isinstance(make_classifier(config), LearnedClassifier)


def test_make_classifier_learned_missing_model_falls_back_to_rule(tmp_path: Path) -> None:
    config = _config(
        tmp_path / "c",
        tmp_path / "o",
        classifier_backend="learned",
        classifier_model_path=str(tmp_path / "does-not-exist.json"),
    )
    assert isinstance(make_classifier(config), RuleClassifier)


def test_make_classifier_learned_version_mismatch_falls_back_to_rule(tmp_path: Path) -> None:
    telemetry_dir = _write_recovery_telemetry(tmp_path)
    model_path = tmp_path / "model.json"
    CliRunner().invoke(cli_mod.cli, ["train-classifier", str(telemetry_dir), "-o", str(model_path)])
    data = json.loads(model_path.read_text(encoding="utf-8"))
    data["feature_version"] = "some-old-version"
    model_path.write_text(json.dumps(data), encoding="utf-8")
    config = _config(
        tmp_path / "c",
        tmp_path / "o",
        classifier_backend="learned",
        classifier_model_path=str(model_path),
    )
    assert isinstance(make_classifier(config), RuleClassifier)


# -- run selection: default unchanged, learned routes (6.3) ---------------------


def _recovery_rows(sink: InMemoryTelemetrySink) -> list:
    return [r for r in sink.slide_stage_outcomes if r.classification is not None]


def test_default_run_is_byte_for_byte_unchanged(tmp_path: Path) -> None:
    modes = {"s": "oom"}
    cohort = _cohort(tmp_path, modes)

    default_sink = InMemoryTelemetrySink()
    run_job(
        _config(cohort, tmp_path / "o1"),
        default_sink,
        adapter=FakeAdapter(injections=_injections(modes)),
    )

    explicit_sink = InMemoryTelemetrySink()
    run_job(
        _config(cohort, tmp_path / "o2"),
        explicit_sink,
        adapter=FakeAdapter(injections=_injections(modes)),
        classifier=RuleClassifier(),
    )

    # The recovery telemetry (deterministic fields) is identical under the default and an
    # explicit RuleClassifier — the seam did not change the default path.
    assert [r.signature for r in _recovery_rows(default_sink)] == [
        r.signature for r in _recovery_rows(explicit_sink)
    ]
    assert [r.classification for r in _recovery_rows(default_sink)] == [
        r.classification for r in _recovery_rows(explicit_sink)
    ]
    # A default recovery signature is a rule signature, never a learned one.
    assert all(not r.signature.startswith("learned:") for r in _recovery_rows(default_sink))


def test_learned_classifier_routes_through_learned_signatures(tmp_path: Path) -> None:
    telemetry_dir = _write_recovery_telemetry(tmp_path)
    model_path = tmp_path / "model.json"
    CliRunner().invoke(cli_mod.cli, ["train-classifier", str(telemetry_dir), "-o", str(model_path)])

    modes = {"s": "oom"}
    cohort = _cohort(tmp_path / "run2", modes)
    sink = InMemoryTelemetrySink()
    config = _config(
        cohort,
        tmp_path / "run2" / "out",
        classifier_backend="learned",
        classifier_model_path=str(model_path),
    )
    run_job(config, sink, adapter=FakeAdapter(injections=_injections(modes)))

    rows = _recovery_rows(sink)
    assert rows, "the learned run should still perform recovery"
    assert all(r.signature.startswith("learned:") for r in rows)
