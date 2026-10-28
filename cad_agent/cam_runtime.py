"""The CAM workbench's runtime: FreeCAD's own CAM Python (cad_agent/fccam/Mod/CAM, vendored unchanged) importable over the
stand-ins for FreeCAD's C++ (cad_agent/fcshim/top: FreeCAD, Part, PathApp, PySide, Draft ...) and FreeCAD's libarea and
tsp_solver built as Python modules (ui/libarea/build.sh native). activate() puts them on sys.path once; it is called
inside the `cad cam` commands only, so the CLI's parser never imports them (docs/EDITING_PLAN.md, "CAM in a project")."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHIM = HERE / "fcshim" / "top"
CAM = HERE / "fccam" / "Mod" / "CAM"
_active = False


class CamUnavailable(RuntimeError):
    """The native modules are missing."""


def native_dirs() -> list[Path]:
    out = []
    if os.environ.get("LIBAREA_DIR"):
        out.append(Path(os.environ["LIBAREA_DIR"]))
    out += [HERE / "cam_native", HERE.parent / "ui" / "libarea" / "build"]
    return out


def activate():
    """Make `import FreeCAD, Part, Path, area` resolve to the stand-ins, FreeCAD's CAM Python and libarea."""
    global _active
    if _active:
        return
    for p in (str(CAM), str(SHIM)):
        if p not in sys.path:
            sys.path.insert(0, p)
    for d in native_dirs():
        if any(d.glob("area*.so")) or any(d.glob("area*.pyd")):
            if str(d) not in sys.path:
                sys.path.insert(0, str(d))
            break
    else:
        tried = ", ".join(str(d) for d in native_dirs())
        raise CamUnavailable(f"libarea is not built (looked in {tried}): run ui/libarea/build.sh native")
    os.environ.setdefault("CAD_CAM_USER_DIR", tempfile.mkdtemp(prefix="cad-cam-"))
    _stub_yaml()
    _active = True


def _stub_yaml():
    """Path.Tool's YAML tool bit serializer imports PyYAML at import time; without PyYAML it gets a module whose
    load and dump say so (no Job here reads or writes YAML tool bits)."""
    import importlib.util
    import types
    if importlib.util.find_spec("yaml") is not None:
        return
    m = types.ModuleType("yaml")

    def _missing(*a, **k):
        raise RuntimeError("YAML tool bits need PyYAML, which is not installed")
    for name in ("safe_load", "load", "dump", "safe_dump", "YAMLError"):
        setattr(m, name, _missing)
    m.YAMLError = type("YAMLError", (Exception,), {})
    sys.modules["yaml"] = m
