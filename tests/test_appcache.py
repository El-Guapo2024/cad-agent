"""The user cache (appcache.py, `cad cache`): FreeCAD's ApplicationCache —
size against Preferences' CacheLimit, clearing what's not in use, and the
periodic start-up check."""
from __future__ import annotations

import socket

from cad_agent import appcache, userprefs
from test_cli import run


def _cache(tmp_path, monkeypatch):
    d = tmp_path / "cache"
    d.mkdir()
    monkeypatch.setenv("CAD_WARM_DIR", str(d))
    return d


def test_size_and_to_string(tmp_path, monkeypatch):
    d = _cache(tmp_path, monkeypatch)
    (d / "a.log").write_bytes(b"x" * 2048)
    assert appcache.size() == 2048
    assert appcache.to_string(2048) == "2.00 KB"
    assert appcache.to_string(500 * 1024 * 1024) == "500.00 MB"
    assert appcache.to_string(10) == "10.00 Bytes"


def test_clear_keeps_what_a_running_worker_uses(tmp_path, monkeypatch):
    d = _cache(tmp_path, monkeypatch)
    (d / "warm-old.log").write_text("stale")
    (d / "warm-old.lock").write_text("")
    (d / "warm-live.log").write_text("in use")
    s = socket.socket(socket.AF_UNIX)
    s.bind(str(d / "warm-live.sock"))
    try:
        assert appcache.clear() == len("stale")
        assert sorted(p.name for p in d.iterdir()) == ["warm-live.log", "warm-live.sock", "warm-old.lock"]
    finally:
        s.close()


def test_cad_cache_reports_against_the_limit_and_clears(tmp_path, monkeypatch, capsys):
    d = _cache(tmp_path, monkeypatch)
    (d / "big.log").write_bytes(b"x" * (2 * 1024 * 1024))
    userprefs.set_value("CacheLimit", 1)
    code, data = run(capsys, "cache")
    assert code == 0 and data["over"] and data["bytes"] == 2 * 1024 * 1024 and data["limit"] == 1024 * 1024
    code, data = run(capsys, "cache", "--clear")
    assert code == 0 and data["freed"] == 2 * 1024 * 1024 and data["bytes"] == 0 and not data["over"]


def test_periodic_check(tmp_path, monkeypatch):
    _cache(tmp_path, monkeypatch)
    assert appcache.periodic_check_due()          # never checked: due (FreeCAD's 1000 days)
    assert not appcache.periodic_check_due()      # weekly by default: not again today
    userprefs.set_value("CachePeriod", 0)         # Always
    assert appcache.periodic_check_due()
    userprefs.set_value("CachePeriod", 5)         # Never
    assert not appcache.periodic_check_due()
