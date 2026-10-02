import pytest


@pytest.fixture(autouse=True)
def _isolated_prefs(tmp_path, monkeypatch):
    """Keep every test off the real ~/.cad-agent/preferences.json."""
    monkeypatch.setenv("CAD_PREFS", str(tmp_path / "preferences.json"))
