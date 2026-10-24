# SPDX-License-Identifier: LGPL-2.1-or-later
"""Writes ui/src/attachertexts.ts from FreeCAD's src/Mod/Part/Gui/AttacherTexts.cpp (at 3160daf1e2b6): each
attachment engine's mode captions and tooltips (getUIStrings), and the reference types' names (eRefTypeStrings), as
the Attachment panel (TaskAttacher) shows them.

    python3 ui/scripts/attachertexts.py [AttacherTexts.cpp]

Without an argument the file is fetched from raw.githubusercontent.com at the commit. The C++ is read as it is laid
out: per engine an `if (attacherType.isDerivedFrom(AttachEngine3D...))` branch of `case mmX:` lines, each returning
TwoStrings(qApp->translate(ctx, caption, comment), qApp->translate(ctx, tooltip, comment)), the literals concatenated
as the compiler concatenates them.
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

URL = "https://raw.githubusercontent.com/FreeCAD/FreeCAD/3160daf1e2b6/src/Mod/Part/Gui/AttacherTexts.cpp"
OUT = Path(__file__).resolve().parent.parent / "src" / "attachertexts.ts"
ENGINES = {"AttachEngine3D": "3D", "AttachEnginePlane": "Plane", "AttachEngineLine": "Line",
           "AttachEnginePoint": "Point"}
# Attacher.h's eMapMode, in order (the C++ names to the Python ones)
MM = ["mmDeactivated", "mmTranslate", "mmObjectXY", "mmObjectXZ", "mmObjectYZ", "mmFlatFace", "mmTangentPlane",
      "mmNormalToPath", "mmFrenetNB", "mmFrenetTN", "mmFrenetTB", "mmConcentric", "mmRevolutionSection",
      "mmThreePointsPlane", "mmThreePointsNormal", "mmFolding", "mm1AxisX", "mm1AxisY", "mm1AxisZ", "mm1AxisCurv",
      "mm1Directrix1", "mm1Directrix2", "mm1Asymptote1", "mm1Asymptote2", "mm1Tangent", "mm1Normal",
      "mm1Binormal", "mm1TangentU", "mm1TangentV", "mm1TwoPoints", "mm1Intersection", "mm1Proximity",
      "mm0Origin", "mm0Focus1", "mm0Focus2", "mm0OnEdge", "mm0CenterOfCurvature", "mm0CenterOfMass",
      "mm0Intersection", "mm0Vertex", "mm0ProximityPoint1", "mm0ProximityPoint2", "mm1AxisInertia1",
      "mm1AxisInertia2", "mm1AxisInertia3", "mmInertialCS", "mm1FaceNormal", "mmOZX", "mmOZY", "mmOXY", "mmOXZ",
      "mmOYZ", "mmOYX", "mmParallelPlane", "mmMidpoint", "mmMidPlane"]
NAMES = ["Deactivated", "Translate", "ObjectXY", "ObjectXZ", "ObjectYZ", "FlatFace", "TangentPlane",
         "NormalToEdge", "FrenetNB", "FrenetTN", "FrenetTB", "Concentric", "SectionOfRevolution",
         "ThreePointsPlane", "ThreePointsNormal", "Folding", "ObjectX", "ObjectY", "ObjectZ", "AxisOfCurvature",
         "Directrix1", "Directrix2", "Asymptote1", "Asymptote2", "Tangent", "Normal", "Binormal", "TangentU",
         "TangentV", "TwoPointLine", "IntersectionLine", "ProximityLine", "ObjectOrigin", "Focus1", "Focus2",
         "OnEdge", "CenterOfCurvature", "CenterOfMass", "IntersectionPoint", "Vertex", "ProximityPoint1",
         "ProximityPoint2", "AxisOfInertia1", "AxisOfInertia2", "AxisOfInertia3", "InertialCS", "FaceNormal",
         "OZX", "OZY", "OXY", "OXZ", "OYZ", "OYX", "ParallelPlane", "MidPoint", "MidPlane"]
STR = re.compile(r'"((?:[^"\\]|\\.)*)"')


def literal(text: str) -> str:
    """The C++ string literals in text, concatenated and unescaped."""
    return "".join(json.loads('"' + m.group(1) + '"') for m in STR.finditer(text))


def translates(block: str) -> list[str]:
    """The second argument of each qApp->translate(ctx, text, comment) in block."""
    out = []
    for m in re.finditer(r"qApp->translate\(", block):
        depth, i = 1, m.end()
        args, start = [], i
        while depth:
            c = block[i]
            if c == '"':
                j = i + 1
                while block[j] != '"':
                    j += 2 if block[j] == "\\" else 1
                i = j
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    args.append(block[start:i])
            elif c == "," and depth == 1:
                args.append(block[start:i])
                start = i + 1
            i += 1
        out.append(literal(args[1]))
    return out


def main(argv):
    src = Path(argv[1]).read_text() if len(argv) > 1 else urllib.request.urlopen(URL).read().decode()
    body = src[src.index("TextSet getUIStrings"):src.index("Base::Console().warning(")]
    parts = re.split(r"attacherType\.isDerivedFrom\((\w+)::getClassTypeId\(\)\)", body)
    modes = {}
    for cls, block in zip(parts[1::2], parts[2::2]):
        engine = ENGINES[cls]
        table = {}
        for case in re.split(r"\n\s*case ", block)[1:]:
            mm = case.split(":", 1)[0].strip()
            caption, tooltip = translates(case)[:2]
            table[NAMES[MM.index(mm)]] = [caption, tooltip]
        modes[engine] = table
    refs_block = src[src.index("eRefTypeStrings[] = {"):src.index("QString getShapeTypeText")]
    refs = [literal(m.group(1).split(",")[1]) for m in re.finditer(r"QT_TRANSLATE_NOOP3\(([^)]*)\)", refs_block)]
    head = ("// SPDX-License-Identifier: LGPL-2.1-or-later\n"
            "// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is\n"
            "// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):\n"
            "//   src/Mod/Part/Gui/AttacherTexts.cpp: 2016 Victor Titov (DeepSOIC)\n"
            "// Written by ui/scripts/attachertexts.py from FreeCAD's src/Mod/Part/Gui/AttacherTexts.cpp\n"
            "// (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6; 2016 Victor Titov (DeepSOIC); LGPL-2.1-or-later).\n"
            "// Do not edit: run the script again. The Attachment panel's mode captions and tooltips per attacher\n"
            "// engine (AttacherGui::getUIStrings), and the reference types' names (getShapeTypeText), in eRefType order.\n")
    text = head + "export const MODE_TEXTS: Record<string, Record<string, [string, string]>> = " \
        + json.dumps(modes, indent=1, ensure_ascii=False) + "\n" \
        + "export const REF_TYPE_TEXTS: string[] = " + json.dumps(refs, ensure_ascii=False) + "\n"
    OUT.write_text(text)
    print(OUT, {k: len(v) for k, v in modes.items()}, len(refs), "reference types")


if __name__ == "__main__":
    main(sys.argv)
