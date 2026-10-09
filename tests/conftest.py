import os
import sys
import tempfile

import pytest


@pytest.fixture(autouse=True, scope="session")
def _isolated_env(tmp_path_factory):
    """Keep every test off the user's real folders, whatever the shell that started pytest exports.

    A plugin session exports CAD_PROJECTS, so a test that runs `cad` without --projects would log
    into, or change, someone's real designs; macros, the workbench registry and warm workers would
    land in ~/.cad-agent and ~/.cache/cad-agent. Session scope, so module fixtures see it too.
    """
    with pytest.MonkeyPatch.context() as mp:
        for name in ("CAD_PROJECTS", "CAD_SERVE_URL", "CAD_EVALS"):
            mp.delenv(name, raising=False)
        mp.setenv("CAD_MACRO_DIR", str(tmp_path_factory.mktemp("macros")))
        mp.setenv("CAD_RUNTIME_DIR", str(tmp_path_factory.mktemp("runtime")))
        # Warm workers keep their sockets here, and macOS caps a socket path at 104 bytes.
        mp.setenv("CAD_WARM_DIR", tempfile.mkdtemp(prefix="cadw", dir="/tmp"))
        yield


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
