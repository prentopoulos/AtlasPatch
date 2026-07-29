"""Import-guard and launch tests for the GUI (tasks 6.4, 5.1).

The core CLI import graph must stay streamlit-free (the GUI runtime lives behind the
`orchestrator` extra and is imported only inside `gui/app.py`), and the `gui` subcommand
must launch Streamlit as a subprocess rather than importing it in-process.
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
