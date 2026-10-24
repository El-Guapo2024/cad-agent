"""Licence notices: what the repository derives from FreeCAD and ships from others says so, and the wheel carries it.

  * every file in ui/src starts with `SPDX-License-Identifier: LGPL-2.1-or-later` (the UI is ported from FreeCAD), and a file
    that cites FreeCAD's sources names the ones it follows, with their copyright holders, in a header that ui/NOTICE repeats;
  * the three ports outside ui/ (geom.mass_properties, dxf.py's static sections, appcache.py) carry the notice of the
    FreeCAD file they come from, with its copyright line as that file states it;
  * NOTICE, THIRD_PARTY_LICENSES, ui/LICENSE and ui/NOTICE exist and are in the wheel's licence files, and the three notices
    the UI build writes next to the bundle (LICENSE, NOTICE, THIRD_PARTY_LICENSES.txt) are in its package data and are
    current: copies of ui/LICENSE and ui/NOTICE, and a list of every npm package the bundle uses.

No network and no build: the build itself (npm run build) writes the bundle's files, and these tests hold what it wrote.
"""
import json
import re
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
UI_SRC = REPO / "ui" / "src"
NEXT = REPO / "cad_agent" / "workbench" / "next"
SPDX = "SPDX-License-Identifier: LGPL-2.1-or-later"
FOLLOWS = "Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6)"
# A FreeCAD source file named in a comment: a C++ file, a Qt Designer file, a style sheet, a settings file.
CITES_FREECAD = re.compile(r"\b[A-Z][A-Za-z0-9_]+\.(?:cpp|h|ui|qss|yaml|cfg)\b")
CITED_PATH = re.compile(r"^(?:\s*//|/\*|\s{3})\s{2,}(src/[\w./ +-]+?):\s+\S", re.M)


def ui_src_files():
    return sorted(p for p in UI_SRC.rglob("*") if p.is_file())


def header(path, lines=60):
    return "\n".join(path.read_text(encoding="utf-8").splitlines()[:lines])


def pyproject():
    return tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))


# ─── ui/src ──────────────────────────────────────────────────────────────────

def test_there_are_ui_sources_to_check():
    assert len(ui_src_files()) >= 40 and {p.suffix for p in ui_src_files()} <= {".ts", ".tsx", ".css"}


@pytest.mark.parametrize("path", ui_src_files(), ids=lambda p: p.name)
def test_every_ui_src_file_has_the_spdx_header(path):
    first = path.read_text(encoding="utf-8").splitlines()[:2]
    assert any(SPDX in line for line in first), (
        f"{path.relative_to(REPO)} has no `{SPDX}` in its first lines: ui/ is ported from FreeCAD and every file says so")


@pytest.mark.parametrize("path", ui_src_files(), ids=lambda p: p.name)
def test_a_file_that_cites_freecads_sources_names_the_ones_it_follows_in_its_header(path):
    text = path.read_text(encoding="utf-8")
    if not CITES_FREECAD.search(text):
        return
    head = header(path, 80)
    assert FOLLOWS in head, f"{path.name} cites FreeCAD files but its header does not say which it follows and whose they are"
    paths = CITED_PATH.findall(head)
    bare = re.findall(r"No copyright line in the file: ([^\n]*(?:\n(?:\s*//|\s{3})\s{4,}[^\n]*)*)", head)
    assert paths or bare, f"{path.name}: the header names no FreeCAD file"


def test_the_files_the_headers_name_are_in_ui_notice():
    notice = (REPO / "ui" / "NOTICE").read_text(encoding="utf-8")
    named = set()
    for path in ui_src_files():
        head = header(path, 80)
        named.update(CITED_PATH.findall(head))
        for block in re.findall(r"No copyright line in the file: ([^\n]*(?:\n(?:\s*//|\s{3})\s{4,}[^\n]*)*)", head):
            named.update(re.findall(r"src/[\w./ +-]+?\.(?:ui|qss|yaml|cfg|h|cpp)\b", block))
    assert len(named) > 100
    missing = sorted(p for p in named if p not in notice)
    assert not missing, f"ui/NOTICE does not list {len(missing)} of the files the headers name, among them {missing[:5]}"


def test_ui_notice_names_the_authors_it_ports_from_and_the_other_code_it_follows():
    notice = (REPO / "ui" / "NOTICE").read_text(encoding="utf-8")
    for name in ("Werner Mayer", "Jürgen Riegel", "Kustaa Nyholm", "Joao Matos", "Eivind Kvedalen", "Zheng Lei",
                 "Victor Titov", "Morten Vajhøj", "src/Gui/NaviCube.cpp", "src/Gui/Camera.cpp", "src/Base/Quantity.l",
                 "Kongsberg Oil & Gas Technologies AS", "OPEN CASCADE SAS"):
        assert name in notice, name
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+|\[at\]", notice), "ui/NOTICE leaves out the e-mail addresses FreeCAD's notices carry"


# ─── The ports outside ui/ ───────────────────────────────────────────────────

def test_geom_mass_properties_carries_the_notice_of_massproperties_result_cpp():
    head = header(REPO / "cad_agent" / "geom.py", 25)
    assert "SPDX-License-Identifier: MIT AND LGPL-2.1-or-later" in head
    assert "src/Mod/Measure/App/MassPropertiesResult.cpp" in head and "3160daf1e2b62b0472854da4848255c6b3ad554c" in head
    assert "SPDX-FileCopyrightText: 2026 Morten Vajhøj" in head and "mass_properties" in head
    text = (REPO / "cad_agent" / "geom.py").read_text(encoding="utf-8")
    assert text.index("LGPL-2.1-or-later from here") < text.index("def mass_properties")


def test_dxf_py_carries_the_bsd_notice_of_dxf_cpp_and_names_the_templates():
    head = header(REPO / "cad_agent" / "dxf.py", 40)
    assert head.startswith("# SPDX-License-Identifier: MIT AND BSD-3-Clause AND LGPL-2.0-or-later")
    for line in ("src/Mod/Import/App/dxf/dxf.cpp", "SPDX-License-Identifier: BSD-3-Clause", "Copyright (c) 2009, Dan Heeks",
                 "This program is released under the BSD license. See the file COPYING for details.",
                 "modified 2018 wandererfan", "src/Mod/Import/DxfPlate/", "3160daf1e2b62b0472854da4848255c6b3ad554c"):
        assert line in head, line
    doc = (REPO / "cad_agent" / "dxf.py").read_text(encoding="utf-8")
    assert "3160daf1e2b6, LGPL-2.1-or-later) writes a DXF" not in doc, "dxf.cpp is BSD-3-Clause, not LGPL"
    assert "FreeCAD v26.3 20260929" in doc and "re-fitting it" in doc


def test_appcache_py_carries_the_notice_of_applicationcache():
    head = header(REPO / "cad_agent" / "appcache.py", 30)
    assert head.startswith("# SPDX-License-Identifier: LGPL-2.0-or-later")
    for line in ("src/Gui/PreferencePages/DlgSettingsCacheDirectory.cpp", "Copyright (c) 2021 Werner Mayer",
                 "either version 2 of the License, or", "(at your option) any later version", "3160daf1e2b62b0472854da4848255c6b3ad554c"):
        assert line in " ".join(head.replace("\n# ", " ").split()), line


def test_the_python_ports_still_have_their_module_docstring():
    import cad_agent.appcache as appcache
    import cad_agent.dxf as dxf
    import cad_agent.geom as geom
    assert geom.__doc__.startswith("Geometry queries") and appcache.__doc__.startswith("The user cache")
    assert dxf.__doc__.startswith("Laser parts")


# ─── The notice files and the wheel ──────────────────────────────────────────

NOTICE_FILES = ("LICENSE", "NOTICE", "THIRD_PARTY_LICENSES", "ui/LICENSE", "ui/NOTICE")


def test_the_notice_files_exist_and_say_what_they_are_for():
    for name in NOTICE_FILES:
        assert (REPO / name).stat().st_size > 500, name
    notice = (REPO / "NOTICE").read_text(encoding="utf-8")
    for needle in ("MIT", "LGPL-2.1-or-later", "cad_agent/geom.py", "cad_agent/dxf.py", "cad_agent/appcache.py",
                   "cad_agent/materials.py", "MassPropertiesResult.cpp", "dxf.cpp", "DlgSettingsCacheDirectory.cpp",
                   "Morten Vajhøj", "Dan Heeks", "wandererfan", "Werner Mayer", "CC-BY-3.0", "three-cad-viewer", "React",
                   "dockview", "Coin3D", "freecad-icons", "THIRD_PARTY_LICENSES", "FreeCAD.qss",
                   "3160daf1e2b62b0472854da4848255c6b3ad554c"):
        assert needle in notice, needle
    third = (REPO / "THIRD_PARTY_LICENSES").read_text(encoding="utf-8")
    for needle in ("Copyright (c) 2009, Dan Heeks", "Kongsberg Oil & Gas Technologies AS", "Permission is hereby granted",
                   "Neither the name of the copyright holder", "Apache License", "Attribution 3.0 Unported",
                   "Creative Commons Attribution-ShareAlike 2.0", "Creative Commons Attribution-ShareAlike 4.0",
                   "provided 'as-is'", "CC0 1.0 Universal", "Permission to use, copy, modify, and/or distribute",
                   "Mozilla Public License Version 2.0", "Boost Software License - Version 1.0"):
        assert needle in third, needle


def test_pyproject_ships_the_notice_files_in_the_wheel():
    project = pyproject()["project"]
    assert project["license-files"] == list(NOTICE_FILES)
    for licence in ("MIT", "LGPL-2.1-or-later", "LGPL-2.0-or-later", "BSD-3-Clause", "CC-BY-3.0", "CC-BY-SA-4.0", "MPL-2.0", "BSL-1.0"):
        assert licence in project["license"].split(" AND "), licence
    assert pyproject()["build-system"]["requires"][0].startswith("setuptools>=77"), "PEP 639 metadata needs setuptools 77"
    data = pyproject()["tool"]["setuptools"]["package-data"]["cad_agent"]
    for name in ("workbench/next/LICENSE", "workbench/next/NOTICE", "workbench/next/THIRD_PARTY_LICENSES.txt"):
        assert name in data, f"{name} is not in the package data"
    for pattern in data:                                                # every pattern still matches something
        assert list((REPO / "cad_agent").glob(pattern)), pattern


def test_the_bundles_notices_are_there_and_current():
    for name in ("LICENSE", "NOTICE", "THIRD_PARTY_LICENSES.txt"):
        assert (NEXT / name).is_file(), f"cad_agent/workbench/next/{name}: run `npm run build` in ui/"
    assert (NEXT / "LICENSE").read_text(encoding="utf-8") == (REPO / "ui" / "LICENSE").read_text(encoding="utf-8")
    assert (NEXT / "NOTICE").read_text(encoding="utf-8") == (REPO / "ui" / "NOTICE").read_text(encoding="utf-8"), \
        "ui/NOTICE changed since the bundle was built: run `npm run build` in ui/"


def test_the_bundles_licence_file_lists_every_package_the_ui_depends_on_and_gives_each_a_text():
    text = (NEXT / "THIRD_PARTY_LICENSES.txt").read_text(encoding="utf-8")
    dependencies = json.loads((REPO / "ui" / "package.json").read_text(encoding="utf-8"))["dependencies"]
    for name, version in dependencies.items():
        assert re.search(rf"^{re.escape(name)} {re.escape(version)}$", text, re.M), f"{name} {version} is not in the bundle's licences"
    sections = re.findall(r"^-{78}\n(\S+) (\S+)\n", text, re.M)
    listed = re.findall(r"^  (\S+) (\S+)  \S+$", text.split("\nPackages\n", 1)[1].split("\n\n", 1)[0], re.M)
    assert len(sections) == len(listed) >= 40 and sections == listed
    assert text.count("Permission is hereby granted") >= 30
    for inlined in ("postprocessing", "n8ao"):                          # inside three-cad-viewer's published build
        assert inlined in dict(sections)
    assert "Zlib" in text and "Raoul van Rüschen" in text


def test_the_bundles_icons_carry_their_licence_and_readme():
    icons = NEXT / "freecad-icons"
    assert (icons / "LICENSE").is_file() and (icons / "README.md").is_file()
    assert len(list(icons.glob("*.svg"))) == 203
