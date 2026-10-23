#!/usr/bin/env python3
"""The Preferences pages of the workbench against the real FreeCAD's, widget by widget.

    python3 ui/scripts/fcprefsdiff.py FCPREFS.json OURSPREFS.json [PAGE ...] [--tol 1] [--values] [--all]

FCPREFS.json is fcprefs.py's dump of the real FreeCAD 26.3 and OURSPREFS.json oursprefs.mjs's of the workbench. Widgets are matched by the object
name FreeCAD's .ui gives them (ours carry it as data-qf). Per page it prints the widgets FreeCAD shows that ours does not (and the other way
round), and those whose rectangle in the page differs by more than --tol pixels (x, y, width, height), and with --values the ones whose text,
checked state, value or enabled state differs: a setting whose default is not FreeCAD's, a greyed-out one that shows another value than FreeCAD's.
DELIBERATE below lists the differences that are intended; they are shown as such, not as findings. Exit 1 if there is any other difference.
"""
import json
import re
import sys

# widgets whose value is deliberately not FreeCAD's: object name -> why (PARITY.md says the same)
DELIBERATE = {
    "naviCubeToNearest": "NaviRotateToNearest is off by default here (the owner's choice, PARITY.md, Mouse and navigation cube)",
    # FreeCAD's Selection page draws these three unchecked in a fresh profile (the .ui gives them no `checked`) though TreeParams.py defaults them to true and
    # the tree does what they say: the page here shows what the tree does
    "checkBoxAutoSwitch": "FreeCAD draws it unchecked in a fresh profile, though TreeParams' SyncView is true: here it shows what the tree does (PARITY.md, Preferences)",
    "checkBoxAutoExpand": "FreeCAD draws it unchecked in a fresh profile, though TreeParams' SyncSelection is true: here it shows what the tree does (PARITY.md, Preferences)",
    "checkBoxRecord": "FreeCAD draws it unchecked in a fresh profile, though TreeParams' RecordSelection is true: here it shows what the tree does (PARITY.md, Preferences)",
    "checkLogging": "log messages are recorded by default here, since the agent's activity is logged at that level (PARITY.md, Preferences)",
    "AutoloadModuleCombo": "the workbench that starts is CAD Agent, not Part Design (PARITY.md, Preferences)",
}


def rgba(css):
    """The first colour of a swatch's CSS background, as (r, g, b, alpha)."""
    m = re.search(r"rgba?\((\d+), (\d+), (\d+)(?:, ([\d.]+))?\)", css or "")
    return (int(m[1]), int(m[2]), int(m[3]), float(m[4]) if m[4] is not None else 1.0) if m else None


def norm(s):
    return re.sub(r"\s+", " ", (s or "").replace("&", "")).strip()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    tol = 1
    if "--tol" in sys.argv:
        tol = int(sys.argv[sys.argv.index("--tol") + 1])
        args = [a for a in args if a != str(tol)]
    fc = json.load(open(args[0]))
    ours = json.load(open(args[1]))
    # the Colors page with a gradient chosen (fcprefs_dump.py's extras, oursprefs.mjs's states): pages "colors.gradient", "colors.radial", "colors.gradient-mid"
    for key, page in list(ours["pages"].items()):
        for tag, st in (page.get("states") or {}).items():
            ours["pages"][f"{key}.{tag}"] = st
            f = (fc["pages"].get(key, {}).get("extras") or {}).get("states", {}).get(tag)
            if f:
                fc["pages"][f"{key}.{tag}"] = f
    pages = args[2:] or list(ours["pages"])
    bad = 0
    for key in pages:
        f, o = fc["pages"].get(key), ours["pages"].get(key)
        if not f or not o:
            print(f"## {key}: not in {'FreeCAD' if not f else 'ours'}'s dump")
            continue
        fw = {w["name"]: w for w in f["widgets"] if w["name"] and w["visible"]}
        ow = {n: w for n, w in o["widgets"].items() if w["visible"]}
        missing = [n for n in fw if n not in ow]
        extra = [n for n in ow if n not in fw]
        moved = []
        for n, w in fw.items():
            if n not in ow:
                continue
            a, b = w["rect"], ow[n]["rect"]
            d = [b[i] - a[i] for i in range(4)]
            if max(abs(x) for x in d) > tol:
                moved.append((n, a, b, d))
        vals = []
        if "--values" in flags or "--all" in flags:
            for n, w in fw.items():
                if n not in ow:
                    continue
                v = ow[n]
                why = DELIBERATE.get(n)
                # checked state
                if "checked" in w and (w.get("checkable") or "checkable" not in w) and "checked" in v and bool(w["checked"]) != bool(v["checked"]):
                    vals.append((n, f"checked: FreeCAD {w['checked']}, ours {v['checked']}", why))
                # text of a label, check box, button, spin box
                if v.get("kind") in ("label", "checkbox", "radio", "button") and w.get("text") is not None and norm(v.get("text")) != norm(re.sub(r"<[^>]+>", "", w["text"])):
                    vals.append((n, f"text: FreeCAD {norm(w['text'])!r}, ours {norm(v.get('text'))!r}", why))
                if v.get("kind") == "spin" and "text" in w and norm(w["text"]) != norm(v["text"]):
                    vals.append((n, f"value: FreeCAD {w['text']!r}, ours {v['text']!r}", why))
                if v.get("kind") == "combo" and "currentText" in w and norm(w["currentText"]) != norm(v["text"]):
                    vals.append((n, f"selected: FreeCAD {w['currentText']!r}, ours {v['text']!r}", why))
                # a line edit's text (the location, the date format, the licence URL, the shortcut modifiers)
                if v.get("kind") == "edit" and w.get("text") is not None and not re.search(r"/(Users|private|var|tmp|home)/", w["text"]) and norm(w["text"]) != norm(v.get("text")):
                    vals.append((n, f"text: FreeCAD {norm(w['text'])!r}, ours {norm(v.get('text'))!r}", why))
                # a colour button's colour (FreeCAD's #aarrggbb against the swatch's background)
                if v.get("kind") == "color" and w.get("color"):
                    a = rgba(v.get("color", ""))
                    want = (int(w["color"][3:5], 16), int(w["color"][5:7], 16), int(w["color"][7:9], 16), int(w["color"][1:3], 16) / 255)
                    if a is None or a[:3] != want[:3] or abs(a[3] - want[3]) > 0.01:
                        vals.append((n, f"colour: FreeCAD {w['color']}, ours {v.get('color')}", why))
                # enabled here but not in FreeCAD (the other way, disabled here as n/a, is the point of those controls)
                if w.get("enabled") is False and v.get("disabled") is False and v.get("kind") not in ("group", "other", "node", "sheet"):
                    vals.append((n, "enabled: FreeCAD disabled, ours enabled", why))
        print(f"## {key}: {len(fw)} widgets in FreeCAD, {len(ow)} in ours; {len(missing)} missing, {len(extra)} extra, {len(moved)} moved by more than {tol} px, {len(vals)} values differ")
        for n in missing:
            print(f"  MISSING {n} {fw[n]['cls']} {fw[n]['rect']} {fw[n].get('text') or fw[n].get('title') or ''!r}")
            bad += 1
        for n in extra:
            print(f"  extra   {n} {ow[n]['kind']} {ow[n]['rect']}")
        for n, a, b, d in sorted(moved, key=lambda m: (m[1][1], m[1][0])):
            print(f"  MOVED   {n:34} FreeCAD {a}  ours {b}  diff {d}")
            bad += 1
        for n, what, why in vals:
            print(f"  {'deliberate' if why else 'VALUE':10} {n:34} {what}" + (f"  ({why})" if why else ""))
            bad += 0 if why else 1
        if f["rect"][2:] != o["page"]["rect"][2:] and abs(f["rect"][2] - o["page"]["rect"][2]) > tol:
            print(f"  page width: FreeCAD {f['rect'][2]}, ours {o['page']['rect'][2]}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
