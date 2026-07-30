"""Import-guard and launch tests for the GUI and the orchestrator backends (tasks 6.4, 6.1).

The core CLI import graph must stay free of every heavy `orchestrator`-extra dependency — and,
since phase 9 retired Streamlit for a static React bundle, free of any GUI runtime at all — plus
the phase-4 distribution backends (the A2A SDK, Google ADK, and the BigQuery client), each of
which is imported only inside its own guarded module. The `gui` subcommand serves the vendored
static bundle over a stdlib HTTP server, importing no GUI runtime in-process.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from click.testing import CliRunner

from atlas_conductor import cli as cli_mod


def test_importing_the_core_cli_does_not_import_streamlit() -> None:
    # Streamlit is gone entirely (phase 9), but the guard stays as a regression tripwire: no
    # code path may reintroduce a GUI runtime into the core import graph. Run in a clean
    # interpreter, mirroring the phase-2 egress/no-array guards.
    code = (
        "import atlas_conductor.cli, sys; "
        "assert 'streamlit' not in sys.modules, "
        "'streamlit leaked into the core CLI import graph'"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_importing_the_core_cli_does_not_import_distribution_backends() -> None:
    # The A2A transport (a2a-sdk + its HTTP stack), Google ADK, and the BigQuery client are
    # imported only inside their own guarded modules (design D-DIST-5). Importing the core CLI
    # must pull in none of them — and, since they may not be installed, a top-level import leak
    # would also fail this subprocess outright. Run for real to see the whole run façade graph.
    forbidden = ["a2a", "google.adk", "google.cloud.bigquery", "fastapi", "uvicorn", "streamlit"]
    code = (
        "import atlas_conductor.cli, atlas_conductor.run, sys; "
        f"leaked = [m for m in {forbidden!r} if m in sys.modules]; "
        "assert not leaked, f'orchestrator backends leaked into the core CLI: {leaked}'"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_importing_the_core_cli_does_not_import_dvc() -> None:
    # The phase-5 DVC lineage backend imports/shells `dvc` only inside its own module's
    # methods (design D-LIN-4); importing the core CLI + run façade must pull in neither
    # `dvc` nor the `dvc_backend` module. Since `dvc` may not be installed (CI does not
    # install it), a top-level import leak would also fail this subprocess outright.
    forbidden = ["dvc", "atlas_conductor.lineage.dvc_backend"]
    code = (
        "import atlas_conductor.cli, atlas_conductor.run, sys; "
        f"leaked = [m for m in {forbidden!r} if m in sys.modules]; "
        "assert not leaked, f'dvc leaked into the core CLI: {leaked}'"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_gui_command_serves_the_vendored_static_bundle(monkeypatch) -> None:
    # The `gui` command serves the prebuilt bundle over a stdlib HTTP server; it must point the
    # server at the vendored web_dist/ inside the package and never import a GUI runtime. We
    # stub the blocking serve helper so the test captures the directory without binding a socket.
    captured: dict[str, object] = {}

    def fake_serve(directory: Path, port: int, open_browser: bool) -> None:
        captured["directory"] = directory
        captured["port"] = port
        captured["open_browser"] = open_browser

    monkeypatch.setattr(cli_mod, "_serve_bundle", fake_serve)

    bundle = Path(cli_mod.__file__).resolve().parent / "gui" / "web_dist"
    if not (bundle / "index.html").exists():
        # Source checkouts may not have built the bundle; the command should say so and exit.
        result = CliRunner().invoke(cli_mod.cli, ["gui"])
        assert result.exit_code != 0
        assert "GUI bundle not found" in result.output
        return

    result = CliRunner().invoke(cli_mod.cli, ["gui", "--no-browser", "--port", "8123"])
    assert result.exit_code == 0
    assert captured["directory"] == bundle
    assert captured["port"] == 8123
    assert captured["open_browser"] is False
