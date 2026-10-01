"""Shared GUI state: FreeCADGui's job (Gui.Selection, Visibility,
SendMsgToActiveView, ViewObject properties) done over HTTP, so a CLI agent
and the person at the UI can point at the same model.

One `GuiBoard` lives on the workbench's `Bench` (serve.py), one entry per
project. Most of it is live-session state: selection, the hover preselect,
the active task panel, the camera, and the commands list a UI publishes for
`cad gui run` — all reset when the server restarts, the same as reopening
FreeCAD and getting no selection or command list back. Two things persist
to `<project>/out/gui.json`, because they are closer to a project setting
than a session: `hidden` (body visibility) and `view_props` / `unselectable`
(per-body ViewObject properties — colour, display mode, transparency, Deviation
and AngularDeflection (tessellation; see RETESSELLATE_PROPS), ... and
Std_ToggleSelectability). `out/` is never part of the design `cad verify`
hashes (see verify.DESIGN), so none of this touches a verdict — which is also
why a Deviation/AngularDeflection change needs serve.py to explicitly redo the
scene (out/scene.json's own staleness check hashes the same DESIGN set).

Note on naming: the UI side's "ViewProps" bag is stored here as `view_props`,
*not* `view`, because `view` is already the camera/projection field in the
GET /api/gui contract (`{"camera": ..., "projection": ...}`). Reusing `view`
for both would collide, so the per-body properties bag got its own name.
"""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

# `cad gui <cmd>` / POST /api/gui/do
CMDS = ("select", "clear", "show", "hide", "view", "fit", "say", "set", "run")

# `cad gui view DIR`: a camera direction, or a projection mode.
VIEW_CAMERA = ("front", "rear", "top", "bottom", "left", "right", "iso",
               "dimetric", "trimetric", "home")
VIEW_PROJECTION = ("ortho", "persp")
# ... or a whole camera, as FreeCAD's "SetCamera" view message takes it and
# Std_ViewIvIssueCamPos prints it: an Inventor OrthographicCamera / PerspectiveCamera node.
_CAMERA_NODE = re.compile(r"^\s*(?:#Inventor[^\n]*)?\s*(Orthographic|Perspective)Camera\s*\{[^{}]*\}\s*$", re.S)


def camera_projection(v: str) -> str | None:
    """'ortho' or 'persp' when `v` is an Inventor camera node, else None."""
    m = _CAMERA_NODE.match(v)
    return None if m is None else ("ortho" if m.group(1) == "Orthographic" else "persp")

# `cad gui run NAME [ARG...]`: NAME must look like a FreeCAD/our command
# (Std_ViewFitAll, CADAgent_Something, ...) — letters, digits, underscore,
# not starting with a digit. Gui.runCommand itself takes no arguments; any
# extra ARGs are passed through untouched, for a UI command that wants them.
COMMAND_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# ViewProviderPartExt's own tessellation properties (FreeCAD src/Mod/Part/Gui/ViewProviderExt.cpp):
# Deviation is a PropertyFloatConstraint (percent of the body's bounding-box size), constrained to
# tessRange = {0.01, 100.0, step 0.01}; AngularDeflection is a PropertyAngle (degrees), constrained
# to angDeflectionRange = {1.0, 180.0, step 0.05}. Their defaults come from loadParameter(), which
# is called once a new object attaches: the "Mod/Part" preferences' MeshDeviation / MeshAngular-
# Deflection, 0.2 / 28.65 when the user never touched that preference (28.65 degrees is ~0.5 rad).
# Unlike every other property below, changing either re-tessellates the body (onChanged ->
# updateVisual()); scene.py and serve.py key off RETESSELLATE_PROPS to know when to redo it.
DEVIATION_RANGE = (0.01, 100.0)
ANGULAR_DEFLECTION_RANGE = (1.0, 180.0)
DEVIATION_DEFAULT = 0.2
ANGULAR_DEFLECTION_DEFAULT = 28.65

# Per-body ViewObject properties (FreeCAD's GuiDocument.xml), keyed the way
# the UI stores them; see FREECAD_PROP_NAMES for `cad gui set`'s own names.
VIEW_PROP_TYPES = {
    "displayMode": ("enum", ("Flat Lines", "Shaded", "Wireframe", "Points")),
    "shapeColor": ("color", None),
    "transparency": ("range", (0, 100)),
    "lineColor": ("color", None),
    "lineWidth": ("number", None),
    "pointColor": ("color", None),
    "pointSize": ("number", None),
    "drawStyle": ("enum", ("Solid", "Dashed", "Dotted", "Dashdot")),
    "lighting": ("enum", ("One side", "Two side")),
    "onTop": ("enum", ("Disabled", "Enabled", "Object", "Element")),
    "selectionStyle": ("enum", ("Shape", "BoundBox")),
    "boundingBox": ("bool", None),
    "showInTree": ("bool", None),
    "showPlacement": ("bool", None),   # ViewProviderDragger::ShowPlacement
    "deviation": ("range", DEVIATION_RANGE),
    "angularDeflection": ("range", ANGULAR_DEFLECTION_RANGE),
}

# Changing either of these re-tessellates the body (see the block comment above).
RETESSELLATE_PROPS = frozenset({"deviation", "angularDeflection"})

# `cad gui set`'s own vocabulary: FreeCAD's ViewObject property names, mapped
# to the keys above. Visibility/Selectable are not stored in view_props: they
# fold into the top-level `hidden` / `unselectable` lists instead.
FREECAD_PROP_NAMES = {
    "DisplayMode": "displayMode", "ShapeColor": "shapeColor", "Transparency": "transparency",
    "LineColor": "lineColor", "LineWidth": "lineWidth", "PointColor": "pointColor",
    "PointSize": "pointSize", "DrawStyle": "drawStyle", "Lighting": "lighting",
    "OnTopWhenSelected": "onTop", "SelectionStyle": "selectionStyle",
    "BoundingBox": "boundingBox", "ShowInTree": "showInTree", "ShowPlacement": "showPlacement",
    "Visibility": "visibility", "Selectable": "selectable",
    "Deviation": "deviation", "AngularDeflection": "angularDeflection",
}
PSEUDO_PROPS = ("visibility", "selectable")       # fold into hidden / unselectable
_FREECAD_NAME = {v: k for k, v in FREECAD_PROP_NAMES.items()}


def fmt_props(props: dict) -> str:
    """The way `cad gui set` takes them: ShapeColor=#ff0000, Transparency=50."""
    def val(key, v):
        if key.endswith("Color") and isinstance(v, int) and not isinstance(v, bool):
            return f"#{v:06x}"
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v)
    return ", ".join(f"{_FREECAD_NAME.get(k, k)}={val(k, v)}" for k, v in sorted(props.items()))
CONNECTED_WINDOW_S = 60.0


class GuiError(ValueError):
    """A bad gui command, name or value; the server answers 400, the CLI exit 3."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _names(value, field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise GuiError(f"{field} must be a list of names")
    return [str(x) for x in value]


def _commands(value) -> list[dict]:
    """The UI's own published `cad gui run` vocabulary, posted to `commands`:
    a list of {name, label, enabled}, every field required and the right
    shape. Session-only (see `post`): never written to out/gui.json."""
    if not isinstance(value, list):
        raise GuiError("commands must be a list of {name, label, enabled}")
    out = []
    for item in value:
        if (not isinstance(item, dict) or not isinstance(item.get("name"), str)
                or not isinstance(item.get("label"), str) or not isinstance(item.get("enabled"), bool)):
            raise GuiError("each command needs a name, a label and enabled (true/false)")
        out.append({"name": item["name"], "label": item["label"], "enabled": item["enabled"]})
    return out


def _parse_color(raw) -> int:
    """#rrggbb, or an int already (0..0xFFFFFF) from the wire."""
    if isinstance(raw, bool):
        raise GuiError("a color is not a bool")
    if isinstance(raw, int):
        if not 0 <= raw <= 0xFFFFFF:
            raise GuiError(f"color must be 0..0xFFFFFF, got {raw!r}")
        return raw
    s = str(raw).strip()
    if s.startswith("#"):
        hexpart = s[1:]
        if len(hexpart) != 6 or any(c not in "0123456789abcdefABCDEF" for c in hexpart):
            raise GuiError(f"color must be #rrggbb, got {raw!r}")
        return int(hexpart, 16)
    parts = s.split(",")
    if len(parts) != 3:
        raise GuiError(f"color must be #rrggbb or r,g,b (0-255), got {raw!r}")
    try:
        r, g, b = (int(p.strip()) for p in parts)
    except ValueError:
        raise GuiError(f"color must be #rrggbb or r,g,b (0-255), got {raw!r}") from None
    if not all(0 <= v <= 255 for v in (r, g, b)):
        raise GuiError(f"color channels must be 0-255, got {raw!r}")
    return (r << 16) | (g << 8) | b


def validate_props(props, allow_pseudo: bool = True) -> dict:
    """Partial<ViewProps> (plus, with allow_pseudo, visibility/selectable) from
    the wire: every key known, every value the right shape. Raises GuiError."""
    if not isinstance(props, dict) or not props:
        raise GuiError("props must be a non-empty object")
    out = {}
    for key, value in props.items():
        if key in PSEUDO_PROPS:
            if not allow_pseudo:
                other = "hidden" if key == "visibility" else "unselectable"
                raise GuiError(f"{key} is not a view property; use the top-level {other!r} list")
            if not isinstance(value, bool):
                raise GuiError(f"{key} must be true or false")
            out[key] = value
            continue
        spec = VIEW_PROP_TYPES.get(key)
        if spec is None:
            raise GuiError(f"unknown view property {key!r} (one of: "
                           f"{', '.join(VIEW_PROP_TYPES)}{', visibility, selectable' if allow_pseudo else ''})")
        kind, extra = spec
        if kind == "enum":
            if value not in extra:
                raise GuiError(f"{key} must be one of {', '.join(extra)}, got {value!r}")
            out[key] = value
        elif kind == "color":
            out[key] = _parse_color(value)
        elif kind == "range":
            lo, hi = extra
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not (lo <= value <= hi):
                raise GuiError(f"{key} must be a number between {lo} and {hi}, got {value!r}")
            out[key] = value
        elif kind == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise GuiError(f"{key} must be a number, got {value!r}")
            out[key] = value
        elif kind == "bool":
            if not isinstance(value, bool):
                raise GuiError(f"{key} must be true or false, got {value!r}")
            out[key] = value
    return out


def coerce_view_prop(fc_name: str, raw: str):
    """`cad gui set`'s Prop=value, FreeCAD's own ViewObject property name and a
    plain-text value -> (internal key, JSON-able value). Raises GuiError."""
    key = FREECAD_PROP_NAMES.get(fc_name)
    if key is None:
        raise GuiError(f"unknown view property {fc_name!r} (one of: {', '.join(FREECAD_PROP_NAMES)})")
    if key in PSEUDO_PROPS:
        v = str(raw).strip().lower()
        if v not in ("true", "false", "1", "0"):
            raise GuiError(f"{fc_name} takes true or false, got {raw!r}")
        return key, v in ("true", "1")
    kind, extra = VIEW_PROP_TYPES[key]
    if kind == "enum":
        if raw not in extra:
            raise GuiError(f"{fc_name} must be one of {', '.join(extra)}, got {raw!r}")
        return key, raw
    if kind == "color":
        return key, _parse_color(raw)
    if kind in ("range", "number"):
        try:
            v = float(raw)
        except ValueError:
            raise GuiError(f"{fc_name} must be a number, got {raw!r}") from None
        if kind == "range":
            lo, hi = extra
            if not (lo <= v <= hi):
                raise GuiError(f"{fc_name} must be between {lo} and {hi}, got {raw!r}")
        return key, v
    if kind == "bool":
        v = str(raw).strip().lower()
        if v not in ("true", "false", "1", "0"):
            raise GuiError(f"{fc_name} takes true or false, got {raw!r}")
        return key, v in ("true", "1")
    raise AssertionError(kind)  # pragma: no cover


def parse_prop_args(values) -> dict:
    """A list of `Prop=value` strings (`cad gui set`'s own syntax, also how a
    `cad gui set ...` macro line writes them) -> a validated {internal_key:
    value} dict via `coerce_view_prop`. Raises GuiError."""
    props = {}
    for item in values:
        key, sep, raw = item.partition("=")
        if not sep or not key:
            raise GuiError(f"cad gui set takes Prop=value, got {item!r}")
        k, v = coerce_view_prop(key, raw)
        props[k] = v
    return props


# ─── out/gui.json ──────────────────────────────────────────────────────────

def _gui_json(pdir: Path) -> Path:
    return Path(pdir) / "out" / "gui.json"


def _load_persisted(pdir: Path) -> dict:
    try:
        data = json.loads(_gui_json(pdir).read_text())
    except (OSError, ValueError):
        data = {}
    hidden = data.get("hidden", [])
    view_props = data.get("view_props", {})
    unselectable = data.get("unselectable", [])
    return {
        "hidden": sorted({str(x) for x in hidden}) if isinstance(hidden, list) else [],
        "view_props": {str(b): dict(p) for b, p in view_props.items()}
        if isinstance(view_props, dict) else {},
        "unselectable": sorted({str(x) for x in unselectable}) if isinstance(unselectable, list) else [],
    }


def load_view_props(pdir: Path) -> dict:
    """Every body's current view_props, straight from out/gui.json — the durable
    store a GuiBoard writes synchronously on every mutation (post/do), so this is
    accurate even with no server running. scene.py reads it to tessellate each
    body with its own Deviation/AngularDeflection (FreeCAD's defaults when a body
    has neither set)."""
    return _load_persisted(pdir)["view_props"]


def save_persisted(pdir: Path, hidden, view_props, unselectable) -> Path:
    path = _gui_json(pdir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"hidden": sorted(set(hidden)), "view_props": view_props,
              "unselectable": sorted(set(unselectable))}
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    tmp.replace(path)
    return path


def _default(pdir: Path) -> dict:
    p = _load_persisted(pdir)
    return {"selected": [], "preselected": None, "hidden": p["hidden"], "task": None,
            "view": {"camera": None, "projection": None},
            "view_props": p["view_props"], "unselectable": p["unselectable"], "commands": [],
            "camera_node": None, "updated": None}


class GuiBoard:
    """Every project's shared GUI state, held in memory by the workbench."""

    def __init__(self):
        self.lock = threading.Lock()
        self._state: dict[str, dict] = {}
        self._posted: dict[str, float] = {}

    def _slot(self, slug: str, pdir: Path) -> dict:
        if slug not in self._state:
            self._state[slug] = _default(pdir)
        return self._state[slug]

    def connected(self, slug: str, live_clients: int) -> bool:
        posted = self._posted.get(slug)
        recent = posted is not None and (time.time() - posted) < CONNECTED_WINDOW_S
        return bool(recent or live_clients > 0)

    def get(self, slug: str, pdir: Path, live_clients: int) -> dict:
        with self.lock:
            s = self._slot(slug, pdir)
            return {"slug": slug, "connected": self.connected(slug, live_clients),
                    "selected": list(s["selected"]), "preselected": s["preselected"],
                    "hidden": list(s["hidden"]), "task": s["task"], "view": dict(s["view"]),
                    "view_props": {b: dict(p) for b, p in s["view_props"].items()},
                    "unselectable": list(s["unselectable"]),
                    "commands": [dict(c) for c in s["commands"]], "camera_node": s.get("camera_node"),
                    "updated": s["updated"]}

    def post(self, slug: str, pdir: Path, patch: dict) -> None:
        """A UI pushing its own live state. Partial: only given keys change."""
        if not isinstance(patch, dict):
            raise GuiError("state must be an object")
        with self.lock:
            s = self._slot(slug, pdir)
            persisted = False
            if "selected" in patch:
                s["selected"] = _names(patch["selected"], "selected")
            if "preselected" in patch:
                v = patch["preselected"]
                s["preselected"] = None if v is None else str(v)
            if "hidden" in patch:
                s["hidden"] = _names(patch["hidden"], "hidden")
                persisted = True
            if "task" in patch:
                v = patch["task"]
                s["task"] = None if v is None else str(v)
            if "view" in patch:
                v = patch["view"]
                if not isinstance(v, dict):
                    raise GuiError("view must be an object")
                if "camera" in v:
                    s["view"]["camera"] = None if v["camera"] is None else str(v["camera"])
                if "projection" in v:
                    s["view"]["projection"] = None if v["projection"] is None else str(v["projection"])
            if "view_props" in patch:
                vp = patch["view_props"]
                if not isinstance(vp, dict):
                    raise GuiError("view_props must be {body: {property: value}}")
                for body, props in vp.items():
                    merged = dict(s["view_props"].get(body, {}))
                    merged.update(validate_props(props, allow_pseudo=False))
                    s["view_props"][str(body)] = merged
                persisted = True
            if "unselectable" in patch:
                s["unselectable"] = _names(patch["unselectable"], "unselectable")
                persisted = True
            if "commands" in patch:
                s["commands"] = _commands(patch["commands"])    # session-only: never persisted
            if "camera_node" in patch:   # the UI's camera as "GetCamera" writes it (session-only)
                v = patch["camera_node"]
                if v is not None and not (isinstance(v, str) and camera_projection(v)):
                    raise GuiError("camera_node must be an Inventor camera node")
                s["camera_node"] = v
            if persisted:
                save_persisted(pdir, s["hidden"], s["view_props"], s["unselectable"])
            s["updated"] = _now()
            self._posted[slug] = time.time()

    def do(self, slug: str, pdir: Path, cmd: str, args: list[str], props: dict | None = None):
        """One `cad gui <cmd>` / POST /api/gui/do action. Returns (summary, files)
        for the activity log; the caller broadcasts the event."""
        if cmd not in CMDS:
            raise GuiError(f"unknown gui command {cmd!r} (one of: {', '.join(CMDS)})")
        args = [str(a) for a in args]
        with self.lock:
            s = self._slot(slug, pdir)
            files: list[str] = []
            if cmd == "select":
                s["selected"] = list(args)
                summary = f"selected {', '.join(args)}" if args else "selected none"
            elif cmd == "clear":
                if args:
                    raise GuiError("clear takes no arguments")
                s["selected"] = []
                summary = "cleared the selection"
            elif cmd in ("show", "hide"):
                if not args:
                    raise GuiError(f"{cmd} needs at least one name")
                hidden = set(s["hidden"])
                (hidden.update if cmd == "hide" else hidden.difference_update)(args)
                s["hidden"] = sorted(hidden)
                files.append(str(save_persisted(pdir, s["hidden"], s["view_props"], s["unselectable"])))
                summary = f"{cmd} {', '.join(args)}"
            elif cmd == "view":
                if len(args) != 1:
                    raise GuiError("view takes exactly one direction or projection")
                v = args[0]
                if v in VIEW_PROJECTION:
                    s["view"]["projection"] = v
                elif v in VIEW_CAMERA:
                    s["view"]["camera"] = v
                elif camera_projection(v):
                    s["view"]["camera"] = v
                    s["view"]["projection"] = camera_projection(v)
                else:
                    raise GuiError(f"unknown view {v!r} (one of: "
                                   f"{', '.join((*VIEW_CAMERA, *VIEW_PROJECTION))}, or an Inventor camera node)")
                summary = f"view {v}"
            elif cmd == "fit":
                if args not in ([], ["selection"]):
                    raise GuiError("fit takes no arguments, or 'selection'")
                summary = "fit " + (args[0] if args else "all")
            elif cmd == "say":
                if not args:
                    raise GuiError("say needs text")
                summary = " ".join(args)
            elif cmd == "set":
                if len(args) != 1:
                    raise GuiError("set takes exactly one body name")
                body = args[0]
                checked = validate_props(props, allow_pseudo=True)
                vis = checked.pop("visibility", None)
                sel = checked.pop("selectable", None)
                if checked:
                    merged = dict(s["view_props"].get(body, {}))
                    merged.update(checked)
                    s["view_props"][body] = merged
                if vis is not None:
                    hidden = set(s["hidden"])
                    (hidden.discard if vis else hidden.add)(body)
                    s["hidden"] = sorted(hidden)
                if sel is not None:
                    unsel = set(s["unselectable"])
                    (unsel.discard if sel else unsel.add)(body)
                    s["unselectable"] = sorted(unsel)
                files.append(str(save_persisted(pdir, s["hidden"], s["view_props"], s["unselectable"])))
                bits = [f"{k}={v}" for k, v in checked.items()]
                if vis is not None:
                    bits.append(f"visibility={vis}")
                if sel is not None:
                    bits.append(f"selectable={sel}")
                summary = f"set {body}: {', '.join(bits)}"
            elif cmd == "run":
                if not args:
                    raise GuiError("run needs a command name")
                name = args[0]
                if not COMMAND_NAME_RE.fullmatch(name):
                    raise GuiError("a command name is letters, digits and underscore only "
                                   f"(Std_…, CADAgent_…), got {name!r}")
                summary = "run " + " ".join(args)
            else:  # pragma: no cover - CMDS is exhaustive above
                raise AssertionError(cmd)
            s["updated"] = _now()
            self._posted[slug] = time.time()
        return summary, files
