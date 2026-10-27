"""feature_edit's part for attachment: a sketch's AttachmentSupport, MapMode, ... and ExternalGeometry, and the datum
entries (DatumPlane, DatumLine, DatumPoint, LocalCoordinateSystem and the PartDesign:: ones), read from and
written to a part file in place.

read() gives a sketch, besides "support" ("XY", "XZ", "YZ" for a plain FlatFace sketch on an origin plane, else
None), FreeCAD's whole attachment and its external geometry:

    {"attachment_support": [["Pad", "Face6"]], "map_mode": "FlatFace", "attachment_offset": None,
     "map_reversed": False, "map_path_parameter": 0.0, "placement": None, "external_geometry": [["Pad", "Edge3"]]}

A sketch on an origin plane with FlatFace and nothing else is written support="XY", as before; any other attachment
is written with FreeCAD's keywords. The datums (feature_attach._Datum) are feature_kw.KwFeatures, read and edited as
feature_edit reads and edits every one; referenced() serves their order check too.
"""
from __future__ import annotations

import ast
import json

from . import feature as F
from .feature_attach import DATUMS, ORIGIN, SHORT, external_refs, ref_items, support_list

DATUM_KINDS = tuple(DATUMS)
ATTACH_KEYS = ("attachment_support", "map_mode", "attachment_offset", "map_reversed", "map_path_parameter",
               "placement")
SKETCH_KEYS = ("support",) + ATTACH_KEYS + ("external_geometry",)
SIZE_KEYS = {k: tuple(c.SIZE) for k, c in DATUMS.items()}           # PartDesign::Plane's ResizeMode, ...
SIZE_DEFAULTS = {k: v for c in DATUMS.values() for k, v in c.SIZE.items()}


def _E():
    from .feature_edit import FeatureEditError
    return FeatureEditError


def _pairs(v):
    return [[o, s] for o, s in v]


def _jsonable(v):
    if isinstance(v, tuple):
        return [_jsonable(x) for x in v]
    if isinstance(v, list):
        return [_jsonable(x) for x in v]
    return v


def attach_dict(where, kw: dict, engine: str, default_mode=None) -> dict:
    """The attachment keys of read(), normalised, from a call's keywords (values as _lit reads them)."""
    try:
        sup = support_list(where, kw.get("attachment_support"))
    except F.FeatureError as e:
        raise _E()(str(e)) from None
    mode = kw.get("map_mode")
    if mode is None:
        mode = default_mode if sup and default_mode else (None if sup else "Deactivated")
    return {"attachment_support": _pairs(sup), "map_mode": mode,
            "attachment_offset": _jsonable(kw.get("attachment_offset")),
            "map_reversed": bool(kw.get("map_reversed", False)),
            "map_path_parameter": float(kw.get("map_path_parameter", 0.0) or 0.0),
            "placement": _jsonable(kw.get("placement"))}


def sketch_dict(call, src, lit, arg) -> dict:
    """A Sketch(...) call's attachment and external geometry, as read() gives them."""
    name = lit(arg(call, ("name",), "name"), src)
    kw = {k.arg: lit(k.value, src) for k in call.keywords if k.arg in SKETCH_KEYS + ("plane",)}
    sup_node = arg(call, ("name", "support"), "support")
    if sup_node is None:
        sup_node = arg(call, (), "plane")
    sup = lit(sup_node, src) if sup_node is not None else None
    where = f"Sketch {name}"
    if sup is not None and kw.get("attachment_support") is not None:
        raise _E()(f"{where}: give support or attachment_support, not both")
    if sup is None and kw.get("attachment_support") is None and kw.get("map_mode") in (None, "FlatFace"):
        sup = "XY"
    if sup is not None:
        try:
            kw["attachment_support"] = [(F._plane_key(sup) + "_Plane", "")]
        except F.FeatureError as e:
            raise _E()(str(e)) from None
    d = attach_dict(where, kw, "Plane", default_mode="FlatFace")
    try:
        d["external_geometry"] = [list(r) for r in ref_items(external_refs(where, kw.get("external_geometry")))]
    except F.FeatureError as e:
        raise _E()(str(e)) from None
    d["support"] = plain_plane(d)
    return d


def plain_plane(d) -> str | None:
    """"XY" for a sketch that support="XY" says all of: FlatFace on one origin plane, not flipped."""
    sup = d.get("attachment_support") or []
    if len(sup) == 1 and sup[0][1] == "" and str(sup[0][0]).endswith("_Plane") and sup[0][0][:-6] in F.PLANES \
            and d.get("map_mode") in (None, "FlatFace") and not d.get("map_reversed"):
        return sup[0][0][:-6]
    return None


def _ref_src(pairs) -> str:
    from .feature_edit import lit
    return lit([(o, s) for o, s in pairs])


def _place_src(key, v) -> str:
    from .feature_edit import _tuples, lit
    return lit(_tuples("attachment_offset", v))


def merged_sketch(d: dict) -> dict:
    """A sketch dict whose "support" (the old key) and attachment keys may disagree, settled: a support set to a
    plane means FlatFace on it."""
    d = dict(d)
    if d.get("support") and not d.get("attachment_support"):
        d["attachment_support"] = [[F._plane_key(d["support"]) + "_Plane", ""]]
        d.setdefault("map_mode", "FlatFace")
    return d


def attach_kw(d: dict, kind: str) -> list[str]:
    """The keyword arguments a feature's attachment is written with: "support=..." for a plain sketch, else
    FreeCAD's keywords where they are not the defaults."""
    out = []
    raw = d.get("attachment_support") or []
    if not isinstance(raw, str):                    # support_list reads "Pad.Face6", ["Pad", "Face6"], [[...], ...]
        raw = [tuple(r) if isinstance(r, list) else r for r in raw] if not (
            len(raw) == 2 and all(isinstance(x, str) for x in raw)) else raw
    try:
        sup = support_list(d.get("name", ""), raw)
    except F.FeatureError as e:
        raise _E()(str(e)) from None
    mode = d.get("map_mode")
    if kind == "Sketch":
        plane = plain_plane({**d, "attachment_support": _pairs(sup)})
        if plane:
            out.append(f"support={json.dumps(plane)}")
        else:
            if sup:
                out.append(f"attachment_support={_ref_src(sup)}")
            out.append(f"map_mode={json.dumps(mode or ('FlatFace' if sup else 'Deactivated'))}")
    else:
        if sup:
            out.append(f"attachment_support={_ref_src(sup)}")
        if mode is not None and not (mode == "Deactivated" and not sup):
            out.append(f"map_mode={json.dumps(mode)}")
    if d.get("attachment_offset") is not None:
        out.append(f"attachment_offset={_place_src('attachment_offset', d['attachment_offset'])}")
    if d.get("map_reversed"):
        out.append("map_reversed=True")
    if float(d.get("map_path_parameter") or 0.0) != 0.0:
        from .feature_edit import _num
        out.append(f"map_path_parameter={_num(float(d['map_path_parameter']))}")
    if d.get("placement") is not None:
        out.append(f"placement={_place_src('placement', d['placement'])}")
    if kind == "Sketch" and d.get("external_geometry"):
        raw = d["external_geometry"]
        try:
            ext = external_refs(d.get("name", ""), [raw] if isinstance(raw, str) else
                                [r if isinstance(r, str) else tuple(r) for r in raw])
        except F.FeatureError as e:
            raise _E()(str(e)) from None
        from .feature_edit import lit
        out.append(f"external_geometry={lit(ref_items(ext))}")
    return out


# ── edits ──────────────────────────────────────────────────────────────────────────────────────────────

def set_attachment(t, call, kind, current: dict, props: dict, spans, set_arg, drop_kw, arg, pos_names):
    """Rewrite a sketch's attachment keywords for props (any of SKETCH_KEYS / ATTACH_KEYS), in
    place: the keywords that change are set or dropped, the rest of the call is left as it is."""
    new = merged_sketch({**current, **props}) if kind == "Sketch" else {**current, **props}
    if kind == "Sketch" and "support" in props and "attachment_support" not in props:
        if props["support"]:
            new["attachment_support"] = [[F._plane_key(props["support"]) + "_Plane", ""]]
            new["map_mode"] = props.get("map_mode", "FlatFace")
        else:
            new["attachment_support"] = []
    want = {}
    for text in attach_kw({"name": current.get("name"), **new}, kind):
        k, _, v = text.partition("=")
        want[k] = v
    keys = SKETCH_KEYS if kind == "Sketch" else ATTACH_KEYS
    anchor = t.b(call.args[-1]) if call.args else t.b(call.func) + 1     # new keywords go after the name
    new_text = []
    for k in keys:
        node = arg(call, pos_names, k)
        if k in want:
            if node is None:
                new_text.append(f"{k}={want[k]}")
            elif ast.get_source_segment(t.src, node) != want[k]:
                spans.append((t.a(node), t.b(node), want[k]))
        elif node is not None:
            if k == "support" and node not in [kw.value for kw in call.keywords]:
                spans.append((t.a(node), t.b(node), "None"))      # a positional support: keep the others' places
            else:
                drop_kw(t, call, k, spans)
    if new_text:                                    # after the positional arguments (the name), or first
        text = ", " + ", ".join(new_text) if call.args else ", ".join(new_text) + (", " if call.keywords else "")
        spans.append((anchor, anchor, text))
    if kind == "Sketch":
        plane = arg(call, (), "plane")
        if plane is not None:
            drop_kw(t, call, "plane", spans)


def ref_nodes(call, kind) -> list:
    """The string constants of a sketch's or datum's attachment and external geometry that name features:
    (node, name), for rename and for the delete check."""
    out = []
    for k in call.keywords:
        if k.arg not in ("attachment_support", "external_geometry"):
            continue
        v = k.value
        items = v.elts if isinstance(v, (ast.List, ast.Tuple)) else [v]
        if isinstance(v, ast.Tuple) and len(v.elts) == 2 and isinstance(v.elts[0], ast.Constant) and \
                isinstance(v.elts[1], (ast.Constant, ast.List)):
            items = [v]
        for e in items:
            first = e.elts[0] if isinstance(e, (ast.Tuple, ast.List)) and e.elts else e
            if isinstance(first, ast.Constant) and isinstance(first.value, str) and first.value not in ORIGIN \
                    and first.value not in SHORT:
                out.append((first, first.value.split(".")[0]))      # "LCS.XY_Plane" is the LCS's
    return out


def referenced(d: dict) -> list[str]:
    """The features a sketch or datum dict names (its support and external geometry), origin left out."""
    names = [r[0] for r in d.get("attachment_support") or []] + [r[0] for r in d.get("external_geometry") or []]
    return [n.split(".")[0] for n in names if n not in ORIGIN]


def build(d: dict, kind: str = "Sketch") -> dict:
    """A sketch dict's attachment keywords for feature.Sketch, so a bad value is refused as feature.py refuses it."""
    kw = {k: d[k] for k in ATTACH_KEYS if k in d}
    kw["attachment_support"] = [tuple(r) for r in kw.get("attachment_support") or []] or None
    return kw
