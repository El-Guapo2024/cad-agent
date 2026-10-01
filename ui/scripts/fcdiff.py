#!/usr/bin/env python3
"""Differential tests: our ports of FreeCAD logic against the real FreeCAD.

The same cases go through FreeCAD (freecadcmd from the weekly build of main
3160daf1e2b6, the commit PARITY.md ports) and through our TypeScript (bundled for
Node by vite), and every disagreement is printed. Exit status 1 if there are any.

    python3 scripts/fcdiff.py                 # every suite
    python3 scripts/fcdiff.py parse user      # some of: schemas parse user number rotation ypr euler

FREECAD_APP overrides where FreeCAD.app is (default ~/.cad-agent/freecad/FreeCAD.app).
FreeCAD runs with its user files in a temporary folder, never in ~/Library.
"""
import json, math, os, random, re, subprocess, sys, tempfile
from pathlib import Path

UI = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
APP = Path(os.environ.get("FREECAD_APP", "~/.cad-agent/freecad/FreeCAD.app")).expanduser()
SUITES = ["schemas", "parse", "user", "number", "rotation", "ypr", "euler"]
SHOW = int(os.environ.get("FCDIFF_SHOW", "12"))   # disagreements printed per suite
SEQS = ["EulerAngles", "YawPitchRoll"] + [f"{k}_{a}" for k in ("Extrinsic", "Intrinsic")
                                          for a in ("XYZ", "XZY", "YZX", "YXZ", "ZXY", "ZYX", "XYX", "XZX", "YZY", "YXY", "ZXZ", "ZYZ")]

PARSE = [
    "1", "1.5", "-2", "1e3", "1.5e-3", ".5", "5.", "1,5", "1.5.3", "", "abc", "1 mm *", "mm", "2 mm", "2mm",
    "1 m", "2.54 cm", "1 dm", "1 km", "1 um", "1 µm", "1 nm", "1 in", '1"', "1'", "1 ft", "1 yd", "1 mi",
    "1 thou", "1 mil", "3 ft 4 in", "3' 4\"", "1 kg", "1 g", "1 mg", "1 ug", "1 t", "1 lb", "1 oz", "1 st",
    "1 cwt", "1 s", "1 min", "1 h", "1 ms", "1 us", "1 A", "1 mA", "1 kA", "1 MA", "1 K", "1 mK", "1 uK",
    "1 mol", "1 mmol", "1 cd", "1 deg", "1 °", "1 rad", "1 gon", "1 ′", "1 ″", "1°30′", "1 M", "1 AM", "1 AS",
    "1 N", "1 kN", "1 MN", "1 mN", "1 Pa", "1 kPa", "1 MPa", "1 GPa", "1 psi", "1 ksi", "1 Mpsi", "1 bar",
    "1 mbar", "1 Torr", "1 mTorr", "1 uTorr", "1 W", "1 kW", "1 mW", "1 MW", "1 J", "1 kJ", "1 eV", "1 keV",
    "1 MeV", "1 kWh", "1 Ws", "1 cal", "1 kcal", "1 V", "1 kV", "1 mV", "1 Ohm", "1 kOhm", "1 MOhm", "1 mOhm",
    "1 S", "1 kS", "1 mS", "1 uS", "1 F", "1 mF", "1 uF", "1 nF", "1 pF", "1 H", "1 mH", "1 uH", "1 nH",
    "1 T", "1 mT", "1 uT", "1 G", "1 Wb", "1 C", "1 Hz", "1 kHz", "1 MHz", "1 GHz", "1 THz", "1 l", "1 ml",
    "1 cl", "1 dl", "1 mph", "1 sqft", "1 cft", "1 acre", "1 VA", "1 kVA", "1 lbf", "1 kip", "1 slug",
    "1 m + 2 mm", "2 * 3 mm", "10 mm / 2", "1 m^2", "1 mm^2", "1 mm^-1", "1 m/s", "1 m/s^2", "1 kg*m/s^2",
    "1 kg/m^3", "(1+2) mm", "-(3 mm)", "2^3", "2^-1", "sqrt(4)", "sqrt(4 mm^2)", "sin(30)", "cos(0)", "pi",
    "e", "2 pi", "2*pi", "1 mm + 1 kg", "1 mm - 1 s", "1 [a comment] mm", "1 mm [x]", "1/2 in", "1 1/2 in",
    "1 mm^2 / 1 mm", "10 mm * 2 mm", "1 kg mm", "1 mm mm", "+3", "--3", "3 % 2", "mod(5, 3)", "atan2(1, 1)",
    "pow(2, 3)", "1e", "1e+", "1 E3", "1.e3", "0x10", "1_000", "１", "1 mm/(2 s)", "1/(2 mm)", "1 m^(1/2)",
    "1 m^0.5", "1 m^2^2", "-1 mm", "- 1 mm", "1 - -1", "100 %", "1 ft^2", "1 in^3", "1 lb/in^3", "1 W/m/K",
    "1 J/kg/K", "1 N/mm^2", "1 Nm", "1 N*m", "1 kgf", "1 at", "1 atm", "1 inHg", "1 mmHg",
]
UNITS = ["mm", "mm^2", "mm^3", "kg", "kg/mm^3", "deg", "s", "mm/s", "mm/s^2", "N", "N*mm", "Pa", "W", "J", "K",
         "A", "V", "Ohm", "F", "H", "T", "Wb", "C", "S", "1/s", "mol", "cd", "mm^4", "kg*mm^2", "A/mm^2",
         "W/m/K", "J/kg/K", "m^2/s", "W/m^2", "J/K", "kg/s", "1/mm", "1/K", "mm/min"]
VALUES = [0, 1e-12, 1e-9, 3.3e-7, 1e-6, 1e-5, 0.000123, 0.001, 0.0123, 0.1, 1 / 3, 0.5, 2 / 3, 0.999, 1, 1.005,
          2.5, 9.995, 10, 25.4, 99.99, 100, 304.8, 999.9, 1000, 1234.5678, 9999.99, 1e4, 1e5, 1e6, 1e7, 1e9,
          1e12, -1, -25.4, -0.001, -1234.5, -0.0, 0.125, 0.375, 1.0625, 12.345, 0.045, 1e-7, 4.35, 1e15, 1.5e-7]


def unit_quat(rng):   # Shoemake: uniformly random rotations
    u1, u2, u3 = rng.random(), rng.random(), rng.random()
    a, b = math.sqrt(1 - u1), math.sqrt(u1)
    return [a * math.sin(2 * math.pi * u2), a * math.cos(2 * math.pi * u2),
            b * math.sin(2 * math.pi * u3), b * math.cos(2 * math.pi * u3)]


def zyx_quat(y, p, r):   # a plain intrinsic Z-Y'-X'' quaternion, only to make inputs near gimbal lock
    y, p, r = (math.radians(v) / 2 for v in (y, p, r))
    cy, sy, cp, sp, cr, sr = math.cos(y), math.sin(y), math.cos(p), math.sin(p), math.cos(r), math.sin(r)
    return [sr * cp * cy - cr * sp * sy, cr * sp * cy + sr * cp * sy, cr * cp * sy - sr * sp * cy, cr * cp * cy + sr * sp * sy]


def cases():
    rng = random.Random(3160)
    user = [{"value": v, "unit": u, "schema": s, "decimals": d, "denominator": 8}
            for s in range(10) for u in UNITS for v in VALUES for d in (0, 2, 4)]
    user += [{"value": v, "unit": u, "schema": 5, "decimals": 2, "denominator": den}
             for u in ("mm", "mm^2", "mm^3") for v in VALUES for den in (2, 16, 64)]
    s = math.sqrt(0.5)
    rot = [[0, 0, 0, 1], [s, 0, 0, s], [0, s, 0, s], [0, 0, s, s], [1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0],
           [-s, 0, 0, s], [0, -s, 0, s], [0, 0, -s, s], [0, 0, -s, -s], [0, 0, s, -s], [0.5, 0.5, 0.5, 0.5],
           [-0.5, 0.5, -0.5, 0.5]]
    gimbal = [(30, 90, 0), (30, -90, 0), (0, 90, 45), (10, 89.9999, 20), (10, 89.99999999, 20), (10, -89.999999, 5),
              (179.9, 45, -179.9), (180, 0, 0), (-180, 0, 0), (0, 0, 180), (90, 90, 90), (45, 89.97, 0)]
    rot += [zyx_quat(*g) for g in gimbal]
    rot += [unit_quat(rng) for _ in range(300)]
    trip = [(0, 0, 0), (90, 0, 0), (0, 90, 0), (0, -90, 0), (180, 0, 0), (-180, 0, 0), (0, 0, 180), (45, 90, 45),
            (30, 89.9999999, 10), (360, 0, 0), (720, 45, -30), (-30, 120, 10)]
    trip += [tuple(rng.uniform(-180, 180) for _ in range(3)) for _ in range(100)]
    nums = VALUES + [0.125, 0.375, 2.5, 99.5, -0.5, -2.5, 1.5e-5, 0.00012345, 123456789.123, 0.9995, 0.09995, 1e20, 1.25e-10]
    number = [{"value": v, "format": f, "precision": p} for v in nums for f in ("Fixed", "Default") for p in (0, 1, 2, 4, 6)]
    return {"parse": PARSE, "user": user, "number": number, "rotation": [{"q": q} for q in rot], "ypr": [list(t) for t in trip],
            "euler": [{"seq": seq, "angles": list(t)} for seq in SEQS for t in trip], "seqs": SEQS}


def freecadcmd():
    for name in ("freecadcmd", "FreeCADCmd"):
        p = APP / "Contents" / "Resources" / "bin" / name
        if p.exists():
            return p
    sys.exit(f"fcdiff: no freecadcmd in {APP} (set FREECAD_APP)")


def run_freecad(inp, out, tmp, n_parse):
    home = Path(tmp) / "fchome"
    home.mkdir()

    def fc(**extra):
        env = {**os.environ, "FCDIFF_IN": str(inp), "FREECAD_USER_HOME": str(home), "FREECAD_USER_DATA": str(home / "data"),
               "FREECAD_USER_TEMP": str(home / "tmp"), **{f"FCDIFF_{k}": str(v) for k, v in extra.items()}}
        return subprocess.run([str(freecadcmd()), str(HERE / "fcdiff_fc.py")], env=env, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=600)

    # Quantity("1 mm + 1 kg") throws a C++ UnitsMismatchError straight through the Python binding,
    # which stops the script: take its message as that case's answer and go on from the next one.
    lines, parsed = Path(tmp) / "parse.jsonl", []
    while len(parsed) < n_parse:
        r = fc(PHASE="parse", START=len(parsed), OUT=lines)
        if lines.exists():
            parsed += [json.loads(x) for x in lines.read_text().splitlines()]
            lines.unlink()
        if len(parsed) < n_parse:
            m = re.search(r"Exception while processing file: .*? \[(.*)\]", r.stdout + r.stderr)
            if not m:
                sys.exit(f"fcdiff: FreeCAD stopped (exit {r.returncode})\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
            parsed.append({"error": m.group(1), "kind": "uncaught"})
    r = fc(OUT=out)
    if not Path(out).exists():
        sys.exit(f"fcdiff: FreeCAD wrote nothing (exit {r.returncode})\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    data = json.loads(Path(out).read_text())
    data["parse"] = parsed
    Path(out).write_text(json.dumps(data))


def run_ours(inp, out):
    bundle = UI / "node_modules" / ".fcdiff" / "fcdiff.mjs"
    build = ("import('vite').then((v) => v.build({ configFile: false, root: %r, publicDir: false, logLevel: 'error',"
             " build: { ssr: 'scripts/fcdiff-entry.ts', outDir: 'node_modules/.fcdiff', emptyOutDir: true,"
             " rollupOptions: { output: { entryFileNames: 'fcdiff.mjs' } } } }))" % str(UI))
    subprocess.run(["node", "-e", build], cwd=UI, check=True)
    subprocess.run(["node", str(HERE / "fcdiff_ours.mjs"), bundle.as_uri(), str(inp), str(out)], cwd=UI, check=True)


def near(a, b, tol, floor=0.0):
    """Within tol, relative; `floor` makes it absolute near zero (angles, unit vectors)."""
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(near(x, y, tol, floor) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b or abs(a - b) <= tol * max(floor, abs(a), abs(b))
    return a == b


def same(suite, o, f):
    """None if they agree, else what differs."""
    if suite in ("ypr", "euler"):
        if isinstance(o, dict):
            return "error vs value"
        return None if near(o, f, 1e-12, 1) or near([-x for x in o], f, 1e-12, 1) else "quaternion"
    if "error" in o or "error" in f:
        if "error" in o and "error" in f:
            return None if o["error"] == f["error"] else "error message"
        return "error vs value"
    if suite == "number":
        return None if o == f else "text"
    keys = {"parse": ["value", "dims"], "user": ["dims", "text", "unit", "factor"],
            "rotation": ["ypr", "rawAxis", "angle", *SEQS], "schemas": ["name", "description"]}[suite]
    bad = [k for k in keys if not (near(o.get(k), f.get(k), 1e-9, 1) if suite == "rotation" else near(o.get(k), f.get(k), 1e-12))]
    return ", ".join(bad) or None


def known(suite, case, ours, fc):
    """Disagreements that are FreeCAD's undefined behaviour, not ours to copy: why, or None."""
    if suite == "user" and case["unit"] == "deg" and abs(case["value"]) >= 2 ** 31 and fc.get("text", "").startswith("-2147483648"):
        return "toDMS casts degrees past INT_MAX to int (undefined; x86 gives INT_MIN)"
    return None


def main(argv):
    want = [a for a in argv if not a.startswith("-")] or SUITES
    unknown = set(want) - set(SUITES)
    if unknown:
        sys.exit(f"fcdiff: unknown suite(s) {sorted(unknown)}; pick from {SUITES}")
    c = cases()
    with tempfile.TemporaryDirectory(prefix="fcdiff") as tmp:
        inp, fco, ouo = (Path(tmp) / n for n in ("cases.json", "freecad.json", "ours.json"))
        inp.write_text(json.dumps(c))
        run_freecad(inp, fco, tmp, len(c["parse"]))
        run_ours(inp, ouo)
        fc, ours = json.loads(fco.read_text()), json.loads(ouo.read_text())
    failed = 0
    for suite in want:
        inputs = c.get(suite) or fc[suite]
        rows = list(zip(inputs, ours[suite], fc[suite]))
        if suite == "schemas" and len(ours[suite]) != len(fc[suite]):
            print(f"schemas: ours has {len(ours[suite])}, FreeCAD {len(fc[suite])}")
            failed += 1
        diffs = [(i, o, f, why) for i, o, f in rows for why in [same(suite, o, f)] if why]
        excused = {}
        for d in diffs:
            reason = known(suite, *d[:3])
            if reason:
                excused[reason] = excused.get(reason, 0) + 1
        diffs = [d for d in diffs if not known(suite, *d[:3])]
        failed += len(diffs)
        print(f"{suite}: {len(rows)} cases, {len(diffs)} differ"
              + "".join(f" (+{n} known: {why})" for why, n in excused.items()))
        for i, o, f, why in diffs[:SHOW]:
            print(f"  {why}: {json.dumps(i, ensure_ascii=False)}\n    ours    {json.dumps(o, ensure_ascii=False)}\n"
                  f"    FreeCAD {json.dumps(f, ensure_ascii=False)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
