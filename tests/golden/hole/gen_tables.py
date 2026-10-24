"""Writes cad_agent/feature_hole_tables.py: FreeCAD's hole tables, copied out of its sources so they are FreeCAD's exactly.

    python3 tests/golden/hole/gen_tables.py FREECAD_SRC          (a checkout of FreeCAD at 3160daf1e2b6)

From src/Mod/PartDesign/App/FeatureHole.cpp: the thread types and their designations, diameters, pitches and tap drills
(Hole::threadDescription), the clearance holes (metricHoleDiameters, UTSHoleDiameters), the thread class deviations
(ThreadClass_ISOmetric_data), the DIN 76 run-outs (ThreadRunout) and every enumeration; from
src/Mod/PartDesign/Resources/Hole/*.json, the counterbore and countersink definitions Hole::readCutDefinitions reads,
in the order the Linux build lists them (CUT_ORDER below, as `getEnumerationsOfProperty("HoleCutType")` gives them).
"""
import json
import re
import sys
from pathlib import Path

SRC = Path(sys.argv[1])
CPP = (SRC / "src/Mod/PartDesign/App/FeatureHole.cpp").read_text()
OUT = Path(__file__).resolve().parents[3] / "cad_agent" / "feature_hole_tables.py"
# The order the JSON definitions come in, as FreeCAD 26.3 (the Linux AppImage, unpacked) lists the HoleCutType of an
# ISO metric hole: readCutDefinitions takes them in directory order, which the file system decides.
CUT_ORDER = ["iso2009.json", "iso4762.json", "din7984.json", "iso4762-fine.json", "iso10642.json", "iso7046.json",
             "iso10642-fine.json", "iso14583.json", "iso14583part.json", "iso4762_7089.json", "iso12474-fine.json"]


def block(start):
    """The text of the brace-balanced initialiser after `start`."""
    i = CPP.index(start)
    i = CPP.index("{", i)
    depth, j = 0, i
    while True:
        c = CPP[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return CPP[i:j + 1]
        j += 1


def strip_comments(t):
    return re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", t, flags=re.S))


def enums(name):
    m = re.search(r"Hole::" + re.escape(name) + r"\[\]\s*=\s*\{(.*?)\};", CPP, re.S)
    return re.findall(r'"([^"]*)"', strip_comments(m.group(1)))


def num(s):
    return float(s)


# threadDescription: one brace group per thread type, in ThreadTypeEnums order
body = strip_comments(block("const std::vector<Hole::ThreadDescription> Hole::threadDescription[]"))[1:-1]
groups, depth, cur = [], 0, ""
for c in body:
    if c == "{":
        depth += 1
        if depth == 1:
            cur = ""
            continue
    elif c == "}":
        depth -= 1
        if depth == 0:
            groups.append(cur)
            continue
    if depth >= 1:
        cur += c
entry = re.compile(r'\{\s*"([^"]+)"\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\}')
types = enums("ThreadTypeEnums")
threads = {t: [(d, num(a), num(b), num(c)) for d, a, b, c in entry.findall(g)] for t, g in zip(types, groups)}
assert len(groups) == len(types), (len(groups), len(types))

metric = [tuple(num(x) for x in row) for row in re.findall(
    r"\{\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*\}",
    strip_comments(block("const double Hole::metricHoleDiameters[51][4]")))]
uts = [(d, num(a), num(b), num(c)) for d, a, b, c in re.findall(
    r'\{\s*"([^"]+)"\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*\}',
    strip_comments(block("const Hole::UTSClearanceDefinition Hole::UTSHoleDiameters[23]")))]
pairs = re.compile(r"\{\s*([\d.]+)\s*,\s*([\d.]+)\s*\}")
iso_class = [(num(a), num(b)) for a, b in pairs.findall(strip_comments(
    block("const double Hole::ThreadClass_ISOmetric_data[ThreadClass_ISOmetric_data_size][2]")))]
runout = [(num(a), num(b)) for a, b in pairs.findall(strip_comments(
    block("const double Hole::ThreadRunout[ThreadRunout_size][2]")))]
assert len(metric) == 51 and len(uts) == 23 and len(iso_class) == 25 and len(runout) == 24

vec_enums = {}
for name in ("HoleCutType_ISOmetric_Enums", "HoleCutType_ISOmetricfine_Enums"):
    m = re.search(r"std::vector<std::string> Hole::" + name + r"\s*=\s*\{(.*?)\};", CPP, re.S)
    vec_enums[name] = re.findall(r'"([^"]*)"', m.group(1))

cuts = []
for f in CUT_ORDER:
    j = json.loads((SRC / "src/Mod/PartDesign/Resources/Hole" / f).read_text())
    rows = [(r["thread"], float(r["diameter"]), float(r["depth"])) if j["cut_type"] == "counterbore"
            else (r["thread"], float(r["diameter"])) for r in j["data"]]
    cuts.append({"file": f, "name": j["name"], "thread_type": j["thread_type"], "cut_type": j["cut_type"],
                 "angle": float(j["angle"]) if j["cut_type"] == "countersink" else 0.0, "data": rows})
assert {c["file"] for c in cuts} == {p.name for p in (SRC / "src/Mod/PartDesign/Resources/Hole").glob("*.json")}

E = {n: enums(n) for n in ("DepthTypeEnums", "ThreadDepthTypeEnums", "ThreadTypeEnums", "ClearanceNoneEnums",
                           "ClearanceMetricEnums", "ClearanceUTSEnums", "ClearanceOtherEnums", "DrillPointEnums",
                           "HoleCutType_None_Enums", "ThreadClass_None_Enums", "ThreadClass_ISOmetric_Enums",
                           "ThreadClass_ISOmetricfine_Enums", "HoleCutType_UNC_Enums", "ThreadClass_UNC_Enums",
                           "HoleCutType_UNF_Enums", "ThreadClass_UNF_Enums", "HoleCutType_UNEF_Enums",
                           "ThreadClass_UNEF_Enums", "HoleCutType_NPT_Enums", "HoleCutType_BSP_Enums",
                           "HoleCutType_BSW_Enums", "ThreadClass_BSW_Enums", "HoleCutType_BSF_Enums",
                           "ThreadClass_BSF_Enums", "ThreadDirectionEnums")}
E.update(vec_enums)


def fmt(v, ind=4):
    return json.dumps(v)


lines = ['# SPDX-License-Identifier: LGPL-2.1-or-later',
         '#',
         '# Data copied from FreeCAD (https://github.com/FreeCAD/FreeCAD), commit 3160daf1e2b62b0472854da4848255c6b3ad554c:',
         '#   src/Mod/PartDesign/App/FeatureHole.cpp, Copyright (c) 2011 Juergen Riegel <FreeCAD@juergen-riegel.net>',
         '#   src/Mod/PartDesign/Resources/Hole/*.json (the counterbore and countersink definitions)',
         '# under FreeCAD\'s licence, the GNU Lesser General Public License, version 2.1 or (at your option) any later',
         '# version; the text is in ../ui/LICENSE. See ../NOTICE.',
         '# Written by tests/golden/hole/gen_tables.py; do not edit by hand.',
         '"""FreeCAD\'s hole tables (FeatureHole.cpp and Resources/Hole), for cad_agent/feature_hole.py."""',
         '',
         '# Hole::threadDescription: {ThreadType: [(designation, diameter, pitch, tap drill), ...]}',
         'THREADS = {']
for t in types:
    lines.append(f"    {t!r}: [")
    for row in threads[t]:
        lines.append(f"        {row!r},")
    lines.append("    ],")
lines.append("}")
lines.append("# Hole::metricHoleDiameters (ISO 273): (screw diameter, fine, medium, coarse)")
lines.append("METRIC_HOLE_DIAMETERS = [")
lines += [f"    {r!r}," for r in metric]
lines.append("]")
lines.append("# Hole::UTSHoleDiameters (ASME B18.2.8): (designation, close, normal, loose)")
lines.append("UTS_HOLE_DIAMETERS = [")
lines += [f"    {r!r}," for r in uts]
lines.append("]")
lines.append(f"# Hole::ThreadClass_ISOmetric_data (ISO 965-1): (pitch, G deviation)\nTHREAD_CLASS_ISO_DATA = {iso_class!r}")
lines.append(f"# Hole::ThreadRunout (DIN 76-1): (pitch, e1)\nTHREAD_RUNOUT = {runout!r}")
lines.append("# The enumerations, by their names in FeatureHole.cpp")
lines.append("ENUMS = {")
for k, v in E.items():
    lines.append(f"    {k!r}: {v!r},")
lines.append("}")
lines.append("# Resources/Hole/*.json, in readCutDefinitions' order: name, thread_type (metric | metricfine), cut_type")
lines.append("# (counterbore | countersink), angle (a countersink's), data: (thread, diameter[, depth])")
lines.append("CUT_DEFINITIONS = [")
for c in cuts:
    c = dict(c)
    c.pop("file")
    lines.append(f"    {c!r},")
lines.append("]")
OUT.write_text("\n".join(lines) + "\n")
print("wrote", OUT, {t: len(v) for t, v in threads.items()})
