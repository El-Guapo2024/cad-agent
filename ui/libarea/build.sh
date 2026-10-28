#!/usr/bin/env bash
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Builds the CAM workbench's two native Python modules, from FreeCAD's own sources at 3160daf1e2b6, unchanged:
#
#   area        libarea (src/Mod/CAM/libarea: CArea, CCurve, the pocket and offset code, Adaptive2d) with its
#               pybind11 binding pyarea.cpp, over Clipper2 built with USINGZ (src/3rdParty/Clipper2), as FreeCAD's
#               libarea/CMakeLists.txt and cMake/FreeCAD_Helpers/SetupClipper2.cmake build them
#   tsp_solver  src/Mod/CAM/App/tsp_solver.cpp and tsp_solver_pybind.cpp (PathUtils.sort_locations_tsp)
#
#   ui/libarea/build.sh native  ->  ui/libarea/build/area<EXT_SUFFIX> and tsp_solver<EXT_SUFFIX>, which
#                                   cad_agent/cam_native.py puts on sys.path for FreeCAD's CAM Python
#
# Needs a C++20 compiler (FreeCAD builds as C++20), the Python headers of the Python that will import them (PYTHON_INCLUDE, default from
# sysconfig; a folder holding Python.h, and pyconfig.h in it or in PYCONFIG_INCLUDE) and pybind11's headers
# (PYBIND11_INCLUDE, default `python -m pybind11 --includes`, else PLANEGCS_TOOLCHAIN/pybind11-*/include).
# PYTHON picks the Python (default .venv/bin/python, then python3); CXX the compiler; JOBS how many compile at once.
# The only file not FreeCAD's is shim/Precision.hxx: libarea's AreaClipper.cpp includes OCCT's Precision.hxx for
# Precision::Confusion(), given here by FreeCAD's src/Base/Precision.h (OCCT's values).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../.." && pwd)"
target="${1:-native}"
up="$here/upstream"
jobs="${JOBS:-4}"
cxx="${CXX:-c++}"
tc="${PLANEGCS_TOOLCHAIN:-}"

py="${PYTHON:-}"
if [[ -z "$py" ]]; then
    if [[ -x "$root/.venv/bin/python" ]]; then py="$root/.venv/bin/python"; else py="$(command -v python3)"; fi
fi
ext="$("$py" -c 'import sysconfig; print(sysconfig.get_config_var("EXT_SUFFIX"))')"

pyinc="${PYTHON_INCLUDE:-$("$py" -c 'import sysconfig; print(sysconfig.get_paths()["include"])')}"
if [[ ! -f "$pyinc/Python.h" ]]; then
    echo "build.sh: no Python.h in $pyinc: set PYTHON_INCLUDE (and PYCONFIG_INCLUDE) to the headers of $py" >&2
    exit 2
fi
incs=(-I "$pyinc")
if [[ -n "${PYCONFIG_INCLUDE:-}" ]]; then incs+=(-I "$PYCONFIG_INCLUDE"); fi

pb="${PYBIND11_INCLUDE:-}"
if [[ -z "$pb" ]]; then
    pb="$("$py" -c 'import pybind11; print(pybind11.get_include())' 2>/dev/null || true)"
fi
if [[ -z "$pb" && -n "$tc" ]]; then
    pb="$(ls -d "$tc"/pybind11-*/include 2>/dev/null | tail -1 || true)"
fi
if [[ -z "$pb" || ! -f "$pb/pybind11/pybind11.h" ]]; then
    echo "build.sh: pybind11's headers not found: set PYBIND11_INCLUDE (or pip install pybind11)" >&2
    exit 2
fi
incs+=(-I "$pb")

out="$here/build"
obj="$out/obj"
mkdir -p "$obj"
common=(-std=c++20 -O2 -DNDEBUG -fPIC -w -fvisibility=hidden)
clip=(-DUSINGZ -DCLIPPER2_MAX_DECIMAL_PRECISION=8 -I "$up/Clipper2/Clipper2Lib/include" -I "$out/gen")

# clipper.version.h, as Clipper2's CMakeLists.txt configures it from clipper.version.in (PROJECT_VERSION 2.0.1)
mkdir -p "$out/gen/clipper2"
ver="$out/gen/clipper2/clipper.version.h"
if [[ ! -f "$ver" ]]; then
    printf '#ifndef CLIPPER_VERSION_H\n#define CLIPPER_VERSION_H\n\nconstexpr auto CLIPPER2_VERSION = "2.0.1";\n\n#endif  // CLIPPER_VERSION_H\n' > "$ver"
fi

area_sources=(
    "$up/Clipper2/Clipper2Lib/src/clipper.engine.cpp" "$up/Clipper2/Clipper2Lib/src/clipper.offset.cpp"
    "$up/Clipper2/Clipper2Lib/src/clipper.rectclip.cpp" "$up/Clipper2/Clipper2Lib/src/clipper.triangulation.cpp"
    "$up/libarea/Area.cpp" "$up/libarea/AreaOrderer.cpp" "$up/libarea/AreaPocket.cpp" "$up/libarea/Curve.cpp"
    "$up/libarea/AreaClipper.cpp" "$up/libarea/Adaptive.cpp" "$up/libarea/clipper.cpp" "$up/libarea/pyarea.cpp"
)
tsp_sources=("$up/tsp_solver/tsp_solver.cpp" "$up/tsp_solver/tsp_solver_pybind.cpp")

compile() {   # compile <tag> <sources...>: objects in $obj/<tag>-<name>.o, rebuilt when the source is newer
    local tag="$1"; shift
    printf '%s\n' "$@" | xargs -P "$jobs" -I{} sh -c '
        src="$1"; shift; o="$1"; shift; tag="$1"; shift
        f="$o/$tag-$(basename "${src%.cpp}").o"
        if [ ! -f "$f" ] || [ "$src" -nt "$f" ]; then "$@" -c "$src" -o "$f"; fi
    ' _ {} "$obj" "$tag" "$cxx" "${common[@]}" "${clip[@]}" -I "$up/libarea" -I "$up" -I "$here/shim" -I "$up/tsp_solver" "${incs[@]}"
}

objects() {   # objects <tag> <sources...>
    local tag="$1"; shift
    for s in "$@"; do echo "$obj/$tag-$(basename "${s%.cpp}").o"; done
}

build_native() {
    local link=(-shared)
    if [[ "$(uname -s)" == Darwin ]]; then link+=(-undefined dynamic_lookup); fi
    compile area "${area_sources[@]}"
    mapfile -t objs < <(objects area "${area_sources[@]}")
    "$cxx" "${link[@]}" -o "$out/area$ext" "${objs[@]}"
    compile tsp "${tsp_sources[@]}"
    mapfile -t objs < <(objects tsp "${tsp_sources[@]}")
    "$cxx" "${link[@]}" -o "$out/tsp_solver$ext" "${objs[@]}"
    echo "built $out/area$ext $out/tsp_solver$ext"
}

case "$target" in
    native) build_native ;;
    *) echo "usage: build.sh native" >&2; exit 2 ;;
esac
