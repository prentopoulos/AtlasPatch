"""The ``atlaspatch-conduct`` console entry point (task 1.2).

A thin CLI over the run façade. ``run`` plans and executes a job; ``--dry-run`` renders
the reconciled plan and decision trace without dispatching (task 4.5); ``--adapter``
selects the fake adapter (no GPU, the default and CI path) or the real subprocess
adapter (slice A2). Heavy orchestrator dependencies (ADK/A2A/BigQuery) are never
imported here.
"""

from __future__ import annotations

import sys
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
def run(
    config_path: Path,
    adapter: str,
    dry_run: bool,
    trace: str,
    telemetry_dir: Path | None,
) -> None:
    """Plan and execute a job described by CONFIG_PATH (a YAML job config)."""
    try:
        config = load_job_config(config_path)
    except JobConfigError as exc:
        raise click.ClickException(str(exc)) from exc

    sink_dir = telemetry_dir or (config.output_dir / "telemetry")
    telemetry = make_telemetry_sink(config, str(sink_dir))

    if dry_run:
        plan = plan_job(config, telemetry)
        click.echo(build_dry_run_report(plan, telemetry))
        return

    execution_adapter, adapter_name = make_adapter(adapter)
    result = run_job(config, telemetry, execution_adapter, adapter_name)
    click.echo(build_report(result, telemetry, trace=trace))


@cli.command()
@click.argument(
    "telemetry_dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    required=False,
)
def gui(telemetry_dir: Path | None) -> None:
    """Launch the read-only observability GUI (Streamlit) over a TELEMETRY_DIR.

    Shells out to ``streamlit run`` as a subprocess so this CLI process never imports
    ``streamlit`` (the core import graph stays GUI-free — a CI import-guard test enforces
    it). TELEMETRY_DIR is passed to the app via the ``ATLAS_CONDUCTOR_TELEMETRY_DIR`` env
    var; if omitted, the app prompts for it in its sidebar.
    """
    import os
    import subprocess

    app_path = Path(__file__).resolve().parent / "gui" / "app.py"
    env = os.environ.copy()
    if telemetry_dir is not None:
        env["ATLAS_CONDUCTOR_TELEMETRY_DIR"] = str(telemetry_dir)
    command = [sys.executable, "-m", "streamlit", "run", str(app_path)]
    raise SystemExit(subprocess.call(command, env=env))


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
    the sibling cannot diverge from what the GUI shows. Imports no ``streamlit``.
    """
    from atlas_conductor.gui.export import export_report

    click.echo(export_report(telemetry_dir, fmt=fmt))


def main() -> None:
    cli()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(cli())
