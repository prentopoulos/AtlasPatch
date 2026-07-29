"""Import-guard and launch tests for the GUI and the orchestrator backends (tasks 6.4, 6.1).

The core CLI import graph must stay free of every heavy `orchestrator`-extra dependency —
streamlit (GUI), and the phase-4 distribution backends (the A2A SDK, Google ADK, and the
BigQuery client) — each of which is imported only inside its own guarded module. The `gui`
subcommand must launch Streamlit as a subprocess rather than importing it in-process.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from click.testing import CliRunner

from atlas_conductor import cli as cli_mod


def test_importing_the_core_cli_does_not_import_streamlit() -> None:
    # Run in a clean interpreter: the AppTest suite imports streamlit in this process, so an
    # in-process check would be meaningless. Mirrors the phase-2 egress/no-array guards.
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


def test_gui_command_shells_out_to_streamlit(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_call(command, env=None):  # type: ignore[no-untyped-def]
        captured["command"] = command
        captured["env"] = env
        return 0

    monkeypatch.setattr(subprocess, "call", fake_call)
    tele = tmp_path / "tele"
    tele.mkdir()

    result = CliRunner().invoke(cli_mod.cli, ["gui", str(tele)])
    assert result.exit_code == 0

    command = captured["command"]
    assert isinstance(command, list)
    assert "streamlit" in command and "run" in command
    assert str(command[-1]).endswith("app.py")
    env = captured["env"]
    assert isinstance(env, dict)
    assert env["ATLAS_CONDUCTOR_TELEMETRY_DIR"] == str(tele)
