# SPDX-License-Identifier: LGPL-2.1-or-later
"""exprdiff.py's FreeCAD half: runs inside freecadcmd and answers each expression with the real thing.

Each case is evaluated as DocumentObject.evalExpression does it (Expression::parse, then getPyValue on an object that owns
the properties exprdiff_cases.PROPERTIES lists), and the Python object that comes back (or the exception that is raised) is
written as one JSON line, flushed, so a crash or a hang loses only the case it happens on: exprdiff.py goes on from the next one.

    FCDIFF_IN     a JSON file: {"doc": ..., "owner": ..., "props": [[type, name, value], ...], "cases": [expression, ...]}
    FCDIFF_OUT    the JSON lines this writes, one per case
    FCDIFF_META   a JSON file to write which FreeCAD this is into: version, revision, commit, Python, machine
"""
import json
import math
import os
import platform
import re
import sys

import FreeCAD as App

U = App.Units
job = json.load(open(os.environ["FCDIFF_IN"], encoding="utf-8"))
doc = App.newDocument(job["doc"])
obj = doc.addObject("App::FeaturePython", job["owner"])
for typ, name, val in job["props"]:
    obj.addProperty(typ, name, "G")
    setattr(obj, name, val)

if os.environ.get("FCDIFF_META"):
    cfg = App.ConfigGet
    meta = {"version": ".".join(cfg(k) for k in ("BuildVersionMajor", "BuildVersionMinor", "BuildVersionPoint")),
            "revision": cfg("BuildRevision"), "date": cfg("BuildRevisionDate"), "commit": cfg("BuildRevisionHash"),
            "python": platform.python_version(), "system": platform.system(), "machine": platform.machine()}
    with open(os.environ["FCDIFF_META"], "w", encoding="utf-8") as m:
        json.dump(meta, m)


def enc(x):
    """JSON has no inf or nan; -0.0 is kept by repr in the float, so write it as a string too."""
    if math.isnan(x):
        return "nan"
    if math.isinf(x):
        return "inf" if x > 0 else "-inf"
    if x == 0 and math.copysign(1.0, x) < 0:
        return "-0.0"
    return x


def describe(r):
    t = type(r)
    if r is None:
        return {"t": "none"}
    if t is bool:
        return {"t": "bool", "v": r}
    if t is int:
        return {"t": "int", "v": str(r)}
    if t is float:
        return {"t": "float", "v": enc(r)}
    if t is complex:
        return {"t": "complex", "re": enc(r.real), "im": enc(r.imag)}
    if t is str:
        return {"t": "str", "v": r}
    if isinstance(r, U.Quantity):
        return {"t": "quantity", "v": enc(r.Value), "dims": list(r.Unit.Signature)}
    if t in (list, tuple):
        return {"t": t.__name__, "v": [describe(x) for x in r]}
    if isinstance(r, App.Vector):
        return {"t": "vector", "v": [enc(r.x), enc(r.y), enc(r.z)]}
    if isinstance(r, App.Matrix):
        return {"t": "matrix", "v": [enc(x) for x in r.A]}
    if isinstance(r, App.Rotation):
        return {"t": "rotation", "v": [enc(x) for x in r.Q]}
    if isinstance(r, App.Placement):
        return {"t": "placement", "base": [enc(r.Base.x), enc(r.Base.y), enc(r.Base.z)], "q": [enc(x) for x in r.Rotation.Q]}
    return {"t": "other", "type": t.__name__, "str": str(r)}


def message(ex):
    """The text of an exception. Python names the object a SystemError comes from by its address, which differs from run to run: 0x0."""
    return re.sub(r"( object at )0x[0-9a-f]+(>)", r"\g<1>0x0\2", str(ex))


with open(os.environ["FCDIFF_OUT"], "a", encoding="utf-8") as f:
    for text in job["cases"]:
        try:
            res = describe(obj.evalExpression(text))
        except BaseException as ex:   # FreeCAD raises its own exception classes; the type name is part of the answer
            res = {"error": message(ex), "etype": type(ex).__name__}
        f.write(json.dumps(res) + "\n")   # ASCII escapes: a message may hold a lone surrogate, which UTF-8 cannot write
        f.flush()
