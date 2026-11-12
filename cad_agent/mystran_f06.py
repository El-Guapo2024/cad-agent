"""Mystran's results from its printed output (the .F06 next to the .bdf): each grid's displacement, each solid's von
Mises stress at its centre. FreeCAD reads Mystran's results only with the hfcMystranNeuIn add-on it does not ship, so
this is the cad agent's own reading; it is plain text, so the same lines read it in FreeCAD (tests/golden/fem_mystran/
make.py) and here, and pyNastran's reading of the .OP2 Mystran writes alongside must agree with it
(tests/test_fem_mystran_golden.py).
"""
from __future__ import annotations

import re

_HEADING = re.compile(r"^\s*(?:[A-Z] ){3,}[A-Z]")
_NUM = r"([-+]?\d+\.\d*(?:[EeDd][-+]?\d+)?)"
_DISP = re.compile(r"^\s+(\d+)\s+\d+" + r"\s+" + r"\s+".join([_NUM] * 6) + r"\s*$")
_STRESS = re.compile(r"^\s+(\d+)\s+CENTER" + r"\s+" + r"\s+".join([_NUM] * 7) + r"\s*$")


def _f(s):
    return float(s.replace("D", "E").replace("d", "e"))


def read_f06(text):
    """{"displacement": {grid: (T1, T2, T3)}, "displacement_length": {grid: |T|}, "von_mises": {element: σvM}}, of the
    first subcase's tables (the only one FreeCAD's Mystran writer writes)."""
    disp, vm, section = {}, {}, None
    for line in text.splitlines():
        if _HEADING.match(line):
            h = line.replace(" ", "")
            if h.startswith("FORELEMENTTYPE"):         # the stress table's second heading line
                continue
            section = ("disp" if h.startswith("DISPLACEMENTS") else
                       "stress" if h.startswith("ELEMENTSTRESSES") else None)
            continue
        if section == "disp":
            m = _DISP.match(line)
            if m:
                disp.setdefault(int(m.group(1)), tuple(_f(m.group(i)) for i in (2, 3, 4)))
        elif section == "stress":
            m = _STRESS.match(line)
            if m:
                vm.setdefault(int(m.group(1)), _f(m.group(8)))
    if not disp:
        raise ValueError("no displacements in Mystran's output")
    return {"displacement": disp, "displacement_length": {g: sum(c * c for c in t) ** 0.5 for g, t in disp.items()},
            "von_mises": vm}
