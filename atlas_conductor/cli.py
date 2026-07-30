"""The ``atlaspatch-conduct`` console entry point (task 1.2).

A thin CLI over the run façade. ``run`` plans and executes a job; ``--dry-run`` renders
the reconciled plan and decision trace without dispatching (task 4.5); ``--adapter``
selects the fake adapter (no GPU, the default and CI path) or the real subprocess
adapter (slice A2). Heavy orchestrator dependencies (ADK/A2A/BigQuery) are never
imported here.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import click

from atlas_conductor import __version__
from atlas_conductor.config import JobConfigError, load_job_config
from atlas_conductor.report import build_dry_run_report, build_report
from atlas_conductor.run import make_adapter, make_telemetry_sink, plan_job, run_job


@click.group()
@click.version_option(__version__, prog_name="atlaspatch-conduct")
def cli() -> None:
    """Orchestrate AtlasPatch runs at cohort scale."""


@cli.command()
@click.argument("config_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--adapter",
    type=click.Choice(["fake", "real"]),
    default="fake",
    show_default=True,
    help="Execution adapter: 'fake' needs no GPU (default, CI path); 'real' drives the "
    "AtlasPatch CLI as a subprocess.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Reconcile and print the plan and decision trace without dispatching any work.",
)
@click.option(
    "--trace",
    type=click.Choice(["failures", "all", "none"]),
    default="failures",
    show_default=True,
    help="How much of the per-slide decision trace to show in the report.",
)
@click.option(
    "--telemetry-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Directory for the append-only telemetry sink. Defaults to <output_dir>/telemetry.",
)
@click.option(
    "--classifier",
    "classifier_backend",
    type=click.Choice(["rule", "learned"]),
    default=None,
    help="Recovery classifier: 'rule' (default) is the hand-written rules; 'learned' routes "
    "through the model at the config's classifier.model_path. Overrides the config block.",
)
def run(
    config_path: Path,
    adapter: str,
    dry_run: bool,
    trace: str,
    telemetry_dir: Path | None,
    classifier_backend: str | None,
) -> None:
    """Plan and execute a job described by CONFIG_PATH (a YAML job config)."""
    try:
        config = load_job_config(config_path)
    except JobConfigError as exc:
        raise click.ClickException(str(exc)) from exc

    if classifier_backend is not None:
        config = replace(config, classifier_backend=classifier_backend)

    sink_dir = telemetry_dir or (config.output_dir / "telemetry")
    telemetry = make_telemetry_sink(config, str(sink_dir))

    if dry_run:
        plan = plan_job(config, telemetry)
        click.echo(build_dry_run_report(plan, telemetry))
        return

    execution_adapter, adapter_name = make_adapter(adapter)
    result = run_job(config, telemetry, execution_adapter, adapter_name)
    click.echo(build_report(result, telemetry, trace=trace))


def _serve_bundle(directory: Path, port: int, open_browser: bool) -> None:
    """Serve a static directory over a local HTTP server until interrupted (stdlib only).

    Factored out so the ``gui`` command stays a thin wrapper and the launch is testable
    without binding a socket. Uses only ``http.server`` — no GUI runtime is imported.
    """
    import functools
    import http.server
    import socketserver
    import webbrowser

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    with socketserver.TCPServer(("127.0.0.1", port), handler) as httpd:
        url = f"http://127.0.0.1:{httpd.server_address[1]}/"
        click.echo(f"Serving the observability GUI at {url}  (Ctrl-C to stop)")
        if open_browser:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            click.echo("\nStopped.")


@cli.command()
@click.option("--port", default=0, show_default="an open port", help="Port to serve on.")
@click.option("--no-browser", is_flag=True, help="Do not open a browser window.")
def gui(port: int, no_browser: bool) -> None:
    """Serve the static, read-only observability GUI from the packaged bundle.

    Serves the prebuilt React bundle vendored in the wheel over a local HTTP server. The GUI
    renders a bundled demo out of the box; to view a real run, export its snapshot
    (``atlaspatch-conduct export-report <telemetry_dir> --format json > snapshot.json``) and
    load it with the in-page file picker or drag-and-drop. Uses only the standard library, so
    the CLI import graph never pulls in a GUI runtime, and no Node or build step is required.
    """
    bundle = Path(__file__).resolve().parent / "gui" / "web_dist"
    if not (bundle / "index.html").exists():
        raise SystemExit(
            "GUI bundle not found. Install a wheel that ships atlas_conductor/gui/web_dist, "
            "or build it from source with `npm --prefix web ci && npm --prefix web run build`."
        )
    _serve_bundle(bundle, port, open_browser=not no_browser)


@cli.command(name="export-report")
@click.argument("telemetry_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "html"]),
    default="json",
    show_default=True,
    help="The machine-readable report sibling to render (design D18).",
)
def export_report_cmd(telemetry_dir: Path, fmt: str) -> None:
    """Render the HTML/JSON sibling of the report from a TELEMETRY_DIR.

    Reads the append-only telemetry only — the same PHI-free read path the GUI uses — so
    the sibling cannot diverge from what the GUI shows. Imports no ``streamlit``. The JSON
    sibling is the versioned observability *snapshot* — the single machine-readable payload
    (schema version, per-run verdicts, decision trace, cohort metrics, and derived
    choreography and message-flow state) that any renderer consumes (design D-SNAP-3).
    """
    from atlas_conductor.gui.export import export_report

    click.echo(export_report(telemetry_dir, fmt=fmt))


@cli.command(name="export-dossier")
@click.argument("telemetry_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "html"]),
    default="json",
    show_default=True,
    help="The compliance evidence bundle to render (design D-CMP-5).",
)
def export_dossier_cmd(telemetry_dir: Path, fmt: str) -> None:
    """Render a run-scoped compliance evidence bundle from a TELEMETRY_DIR.

    Assembles a PHI-free conformity snapshot — the audit chain verified with
    ``verify_audit_chain`` (reported broken if the trail was tampered with), the run's HITL
    holds/approvals/waivers and telemetry-gate rejections, the per-slide operational outcomes
    and cohort counts, and the control-register summary. Read-only over the same telemetry/audit
    path the GUI and ``export-report`` use, so it cannot diverge from the report. See
    ``COMPLIANCE.md`` for the standing dossier the bundle produces per-run evidence for.
    """
    from atlas_conductor.compliance.evidence import export_dossier

    click.echo(export_dossier(telemetry_dir, fmt=fmt))


@cli.command()
@click.argument("output_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--backend",
    type=click.Choice(["manifest", "dvc"]),
    default="manifest",
    show_default=True,
    help="Lineage backend: 'manifest' is stdlib-only (default, CI path); 'dvc' writes "
    "version-controllable pointers and needs the orchestrator extra.",
)
@click.option(
    "--telemetry-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Directory holding the run's telemetry. Defaults to <output_dir>/telemetry.",
)
def lineage(output_dir: Path, backend: str, telemetry_dir: Path | None) -> None:
    """Record content-addressed, PHI-free lineage over a completed run's OUTPUT_DIR.

    Reads the produced HDF5s under OUTPUT_DIR and the run's telemetry — the same read-only,
    PHI-free path the GUI and export-report use — and writes a lineage manifest (or DVC
    pointers) alongside them. The run's HDF5s and telemetry are left unmodified. ``dvc`` is
    imported only when ``--backend dvc`` is selected (never at CLI import).
    """
    from atlas_conductor.lineage.resolve import LineageResolutionError, from_output_dir
    from atlas_conductor.run import make_lineage_backend

    try:
        run_input = from_output_dir(output_dir, telemetry_dir)
    except LineageResolutionError as exc:
        raise click.ClickException(str(exc)) from exc

    result = make_lineage_backend(backend).record(run_input)
    location = result.manifest_path or output_dir
    click.echo(f"recorded {len(result.records)} lineage record(s) via {backend} -> {location}")


@cli.command(name="train-classifier")
@click.argument("telemetry_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "-o",
    "--output",
    "model_path",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="Path to write the trained JSON model artifact.",
)
@click.option(
    "--seed", type=int, default=0, show_default=True, help="Training seed (deterministic)."
)
def train_classifier_cmd(telemetry_dir: Path, model_path: Path, seed: int) -> None:
    """Train a learned recovery classifier from a TELEMETRY_DIR's recovery dataset.

    Reads the ``slide_stage_outcomes`` family through the same read-only, PHI-free path the GUI
    and ``lineage`` use — it never touches a run's outputs — and writes a committable JSON model
    artifact. Training is deterministic for a fixed dataset and seed.
    """
    from atlas_conductor.classifier.dataset import read_dataset
    from atlas_conductor.classifier.train import train_model
    from atlas_conductor.telemetry import JsonlTelemetrySink

    dataset = read_dataset(JsonlTelemetrySink(telemetry_dir))
    if len(dataset) == 0:
        raise click.ClickException(
            "no labeled recovery rows found in telemetry; run a cohort with failures first"
        )
    out = train_model(dataset, seed=seed).save(model_path)
    click.echo(f"trained on {len(dataset)} recovery row(s) -> {out}")


@cli.command(name="eval-classifier")
@click.argument("telemetry_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--model",
    "model_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Path to the trained JSON model artifact to evaluate.",
)
@click.option(
    "--threshold",
    type=float,
    default=0.6,
    show_default=True,
    help="Abstention confidence threshold for the composed learned classifier.",
)
def eval_classifier_cmd(telemetry_dir: Path, model_path: Path, threshold: float) -> None:
    """Evaluate a learned classifier over a TELEMETRY_DIR, reporting accuracy and safety.

    Reports classification accuracy, per-class precision/recall, and the safety metric — the
    fraction of should-block failures the composed classifier would retry, which is 0 by
    construction of the abstention floor. Read-only; it mutates no run.
    """
    from atlas_conductor.classifier import RuleClassifier
    from atlas_conductor.classifier.dataset import read_dataset
    from atlas_conductor.classifier.evaluate import evaluate, format_report
    from atlas_conductor.classifier.learned import LearnedClassifier
    from atlas_conductor.classifier.model import FeatureVersionMismatch, LinearModel
    from atlas_conductor.telemetry import JsonlTelemetrySink

    dataset = read_dataset(JsonlTelemetrySink(telemetry_dir))
    if len(dataset) == 0:
        raise click.ClickException(
            "no labeled recovery rows found in telemetry to evaluate against"
        )
    try:
        model = LinearModel.load(model_path)
    except FeatureVersionMismatch as exc:
        raise click.ClickException(str(exc)) from exc
    learned = LearnedClassifier(model, fallback=RuleClassifier(), threshold=threshold)
    click.echo(format_report(evaluate(learned, dataset)))


def main() -> None:
    cli()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(cli())
