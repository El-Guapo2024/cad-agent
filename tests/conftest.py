import os
import sys

import pytest


@pytest.fixture(autouse=True)
def _isolated_prefs(tmp_path, monkeypatch):
    """Keep every test off the real ~/.cad-agent/preferences.json."""
    monkeypatch.setenv("CAD_PREFS", str(tmp_path / "preferences.json"))


def cad_env(**extra) -> dict:
    """The environment for a process that runs bin/cad or the warm worker.

    It runs this test's own Python, whatever CAD_PYTHON the shell that started pytest exports: a
    plugin session's CAD_PYTHON is another install's kernel, whose files do not match the ones the
    test makes in-process. And it never inherits CAD_PROJECTS, which would point it at someone's
    real projects. A test that wants a projects folder passes it as `extra`.
    """
    env = {k: v for k, v in os.environ.items() if k != "CAD_PROJECTS"}
    env["CAD_PYTHON"] = sys.executable
    env.update(extra)
    return env
