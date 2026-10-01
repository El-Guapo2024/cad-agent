# fcdiff.py's FreeCAD half: runs inside freecadcmd and answers the cases with the real thing.
import json, math, os
import FreeCAD as App

U = App.Units
cases = json.load(open(os.environ["FCDIFF_IN"]))
out = {}


def err(e):
    return {"error": str(e), "kind": type(e).__name__}


out["schemas"] = [{"num": i, "name": n, "description": U.listSchemas(i)} for i, n in enumerate(U.listSchemas())]


def parse(t):
    try:
        q = U.Quantity(t)
        return {"value": q.Value, "dims": list(q.Unit.Signature)}
    except Exception as e:
        return err(e)


if os.environ.get("FCDIFF_PHASE") == "parse":
    # One line per case, flushed: Quantity's Python constructor lets some C++ exceptions
    # (UnitsMismatchError) escape, which ends this script; fcdiff.py goes on from the next case.
    with open(os.environ["FCDIFF_OUT"], "a") as f:
        for t in cases["parse"][int(os.environ.get("FCDIFF_START", "0")):]:
            f.write(json.dumps(parse(t)) + "\n")
            f.flush()
    raise SystemExit(0)


def user(c):
    try:
        dims = list(U.Quantity("1 " + c["unit"]).Unit.Signature)
    except Exception as e:
        return err(e)
    try:
        q = U.Quantity(c["value"], U.Unit(*dims))
        q.Format = {"Precision": c["decimals"], "Denominator": c["denominator"]}
        text, factor, unit = U.schemaTranslate(q, c["schema"])
        return {"dims": dims, "text": text, "factor": factor, "unit": unit}
    except Exception as e:
        return err(e)


out["user"] = [user(c) for c in cases.get("user", [])]


def number(c):
    # Quantity::toNumber's two formats: Fixed through FreeCAD itself (Quantity.toStr is the same
    # stringstream with std::fixed); Default is the stream's general format, C's %g.
    if c["format"] == "Fixed":
        return U.Quantity(c["value"]).toStr(c["precision"])
    return "%.*g" % (c["precision"], c["value"])


out["number"] = [number(c) for c in cases.get("number", [])]


def pyname(seq):   # Rotation::EulerSequenceNames, what the Python methods take
    kind, _, axes = seq.partition("_")
    return {"EulerAngles": "Euler", "YawPitchRoll": "YawPitchRoll"}.get(seq) or ("I" if kind == "Intrinsic" else "") + axes


def rotation(c):
    r = App.Rotation(*c["q"])
    ax = r.RawAxis
    res = {"ypr": list(r.getYawPitchRoll()), "rawAxis": [ax.x, ax.y, ax.z], "angle": math.degrees(r.Angle)}
    for seq in cases["seqs"]:
        res[seq] = list(r.toEulerAngles(pyname(seq)))
    return res


out["rotation"] = [rotation(c) for c in cases.get("rotation", [])]


def ypr(c):
    r = App.Rotation()
    r.setYawPitchRoll(*c)
    return list(r.Q)


out["ypr"] = [ypr(c) for c in cases.get("ypr", [])]
out["euler"] = [list(App.Rotation(pyname(c["seq"]), *c["angles"]).Q) for c in cases.get("euler", [])]
json.dump(out, open(os.environ["FCDIFF_OUT"], "w"))
