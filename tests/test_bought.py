"""Bought parts must carry provenance. These tests are the enforcement."""
import json

import pytest
from build123d import Box, export_step

from cad_agent import bought as B
from cad_agent import state as st

SLUG = "_test_bought"


@pytest.fixture()
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "ROOT", tmp_path)
    st.project_dir(SLUG, create=True)
    step = tmp_path / "vendor_widget.step"
    export_step(Box(10, 20, 30), str(step))
    return tmp_path, step


def test_step_registers_with_its_source(project):
    _, step = project
    B.register_step(SLUG, "widget", str(step), source="https://vendor.example/widget",
                    vendor="Example Co")
    (row,) = B.list_bought(SLUG)
    assert row["kind"] == "STEP"
    assert row["source"].startswith("https://")
    assert row["vendor"] == "Example Co"


def test_step_without_source_is_refused(project):
    _, step = project
    with pytest.raises(B.MissingProvenance):
        B.register_step(SLUG, "widget", str(step), source="   ")


def test_registering_a_missing_file_raises(project):
    with pytest.raises(FileNotFoundError):
        B.register_step(SLUG, "widget", "/nope/absent.step", source="somewhere")


def test_loaded_step_has_the_vendor_dimensions(project):
    _, step = project
    B.register_step(SLUG, "widget", str(step), source="vendor drawing")
    info = B.bought_info(SLUG, "widget")
    assert info["bbox_mm"] == pytest.approx([10.0, 20.0, 30.0], abs=1e-3)
    assert info["kind"] == "STEP"


def test_step_with_a_stripped_sidecar_is_refused(project):
    _, step = project
    p = B.register_step(SLUG, "widget", str(step), source="vendor drawing")
    p.with_suffix(".json").write_text(json.dumps({}))
    with pytest.raises(B.MissingProvenance):
        B.load_bought(SLUG, "widget")


def test_measured_part_needs_a_source(project):
    tmp, _ = project
    mod = B.bought_dir(SLUG) / "heater.py"
    mod.write_text(
        "from build123d import Cylinder\n"
        "PARAMS = {'dia': 6.35, 'length': 90.0}\n"
        "def build(dia, length):\n"
        "    return Cylinder(dia / 2, length)\n"
    )
    with pytest.raises(B.MissingProvenance):
        B.load_bought(SLUG, "heater")


def test_measured_part_with_a_source_loads(project):
    mod = B.bought_dir(SLUG) / "heater.py"
    mod.write_text(
        'SOURCE = "vendor listing, dimensions table"\n'
        'VENDOR = "Example Heaters"\n'
        "from build123d import Cylinder\n"
        "PARAMS = {'dia': 6.35, 'length': 90.0}\n"
        "def build(dia, length):\n"
        "    return Cylinder(dia / 2, length)\n"
    )
    info = B.bought_info(SLUG, "heater")
    assert info["kind"] == "MEASURED"
    assert info["bbox_mm"][2] == pytest.approx(90.0)
    assert "vendor listing" in info["source"]


def test_unknown_bought_part_names_the_two_routes(project):
    with pytest.raises(FileNotFoundError) as e:
        B.load_bought(SLUG, "ghost")
    assert "register_step" in str(e.value)


def test_a_measured_part_rewritten_within_the_second_runs_its_new_text(project, monkeypatch):
    # Bytecode is reused when the file's mtime (whole seconds) and size match, so a rewrite of the
    # same length in the same second ran the old numbers: state._load_module says why design files
    # are never loaded that way, and bought.py loaded them that way (and left a __pycache__ in
    # the project).
    import os
    import sys
    monkeypatch.setattr(sys, "dont_write_bytecode", False)       # as in a shell that does not set it
    tmp, _ = project
    path = B.register_measured(SLUG, "block", 10, 20, 30, source="datasheet p.1")
    first = B.bought_info(SLUG, "block")["bbox_mm"]
    stamp = path.stat().st_mtime
    path.write_text(path.read_text().replace("'length': 10", "'length': 11"))
    os.utime(path, (stamp, stamp))                               # the same second, the same size
    assert B.bought_info(SLUG, "block")["bbox_mm"] != first
    assert not (path.parent / "__pycache__").exists()


def test_a_bought_part_that_cannot_be_read_is_listed_not_a_crash(project):
    # A truncated sidecar or a measured module with a syntax error made `cad ls` and `cad bought ls`
    # exit 4; the part is listed, as unconfirmed, and loading it still says what is wrong.
    tmp, step = project
    B.register_step(SLUG, "widget", str(step), source="vendor drawing")
    B.register_measured(SLUG, "block", 10, 20, 30, source="datasheet p.1")
    folder = tmp / SLUG / "bought"
    (folder / "widget.json").write_text("{not json")
    (folder / "block.py").write_text("def build(:\n")
    rows = {r["name"]: r for r in B.list_bought(SLUG)}
    assert rows["widget"]["source"] == "UNRECORDED"
    assert rows["block"]["verified"] is False and "cannot load" in rows["block"]["source"]
    with pytest.raises(B.MissingProvenance):
        B.load_bought(SLUG, "widget")
    with pytest.raises(SyntaxError):
        B.load_bought(SLUG, "block")


def test_dot_files_in_bought_are_not_bought_parts(project):
    tmp, step = project
    B.register_step(SLUG, "widget", str(step), source="vendor drawing")
    folder = tmp / SLUG / "bought"
    (folder / ".DS_Store").write_bytes(b"\x00")
    (folder / "._widget.step").write_bytes(b"\x00\x05\x16\x07")
    assert [r["name"] for r in B.list_bought(SLUG)] == ["widget"]
