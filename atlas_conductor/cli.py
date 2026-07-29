"""The ``atlaspatch-conduct`` console entry point (task 1.2).

A thin CLI over the run façade. Slice A1 exposes ``run`` against the fake adapter so
the whole loop is demonstrable with no GPU. The real subprocess adapter and
``--dry-run`` land in slice A2; heavy orchestrator dependencies (ADK/A2A/BigQuery) are
never imported here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from atlas_conductor import __version__
from atlas_conductor.config import JobConfigError, load_job_config
from atlas_conductor.report import build_report
from atlas_conductor.run import run_job
from atlas_conductor.telemetry import JsonlTelemetrySink


@click.group()
@click.version_option(__version__, prog_name="atlaspatch-conduct")
def cli() -> None:
    """Orchestrate AtlasPatch runs at cohort scale."""


@cli.command()
@click.argument("config_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--adapter",
    type=click.Choice(["fake"]),
    default="fake",
    show_default=True,
    help="Execution adapter. Only the fake adapter is available in this slice; the "
    "real subprocess adapter lands in slice A2.",
)
@click.option(
    "--telemetry-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Directory for the append-only telemetry sink. Defaults to " "<output_dir>/telemetry.",
)
def run(config_path: Path, adapter: str, telemetry_dir: Path | None) -> None:
    """Plan and execute a job described by CONFIG_PATH (a YAML job config)."""
    try:
        config = load_job_config(config_path)
    except JobConfigError as exc:
        raise click.ClickException(str(exc)) from exc

    sink_dir = telemetry_dir or (config.output_dir / "telemetry")
    telemetry = JsonlTelemetrySink(sink_dir)
    result = run_job(config, telemetry, adapter_name=adapter)

    click.echo(build_report(result))


def main() -> None:
    cli()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(cli())
