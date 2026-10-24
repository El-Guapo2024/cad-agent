#!/usr/bin/env bash
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Builds the Sketcher solver (FreeCAD's PlaneGCS, ui/planegcs/freecad, and its port of Sketch.cpp,
# sketch.cpp + api.cpp):
#
#   ui/planegcs/build.sh native   ->  ui/planegcs/build/libplanegcs.so (.dylib on macOS), which
#                                     cad_agent/planegcs.py loads through ctypes
#   ui/planegcs/build.sh wasm     ->  ui/planegcs/dist/planegcs.mjs + planegcs.wasm (ES module, no
#                                     pthreads), which ui/src/planegcs.ts loads; committed
#   ui/planegcs/build.sh all      ->  both
#
# It needs Eigen 5.0.0 and Boost (graph, headers only) and, for wasm, Emscripten. Say where:
#   EIGEN_DIR   Eigen's source tree (the directory holding Eigen/): eigen-5.0.0 from
#               https://gitlab.com/libeigen/eigen/-/archive/5.0.0/eigen-5.0.0.tar.gz
#   BOOST_DIR   Boost's headers (the directory holding boost/), e.g. boost_1_86_0
#   EMSDK       an activated emsdk (emsdk 4.0.10 was used for dist/); or have emcc on PATH
# or PLANEGCS_TOOLCHAIN, a directory holding eigen-5.0.0/, boost_1_86_0/ and emsdk/ (on the
# machine dist/ was built on this was ~/work/research/toolchain). Without BOOST_DIR the system's
# /usr/include (apt install libboost-dev) is tried.
# CXX picks the native compiler (default c++).
#
# Why Eigen 5.0.0: FreeCAD 26.3 (3160daf1e2b6) is built with it, and with it the port agrees with
# FreeCAD bit for bit on every case of tests/golden/sketcher. Eigen 3.4.0 builds too, but its
# vectorised kernels round differently in the last bit, and the solver's fallbacks and the drags
# (SQP with BFGS updates) amplify that: about 50 of those cases then differ beyond 1e-9.
#
# PlaneGCS starts one of its QR diagnoses with std::async. Without pthreads (the page cannot be
# cross-origin isolated) libc++'s std::async never returns, so the wasm build force-includes
# shim/deferred_async.h into GCS.cpp, which makes that call std::launch::deferred, as FreeCAD's own
# comment there allows. The vendored files are not changed.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
target="${1:-native}"

tc="${PLANEGCS_TOOLCHAIN:-}"
eigen="${EIGEN_DIR:-${tc:+$tc/eigen-5.0.0}}"
boost="${BOOST_DIR:-${tc:+$tc/boost_1_86_0}}"
emsdk="${EMSDK:-${tc:+$tc/emsdk}}"
if [[ -z "$boost" && -d /usr/include/boost/graph ]]; then boost=/usr/include; fi
if [[ -z "$eigen" || ! -d "$eigen/Eigen" ]]; then
    echo "build.sh: Eigen not found: set EIGEN_DIR (or PLANEGCS_TOOLCHAIN) to eigen-5.0.0" >&2
    exit 2
fi
if ! grep -q 'EIGEN_VERSION_STRING "5.0.0"' "$eigen/Eigen/Version" 2>/dev/null; then
    echo "build.sh: warning: $eigen is not Eigen 5.0.0, FreeCAD's; results will differ from FreeCAD's in the last bits" >&2
fi
if [[ -z "$boost" || ! -d "$boost/boost/graph" ]]; then
    echo "build.sh: Boost not found: set BOOST_DIR (or PLANEGCS_TOOLCHAIN), or apt install libboost-dev" >&2
    exit 2
fi

sources=(
    "$here"/freecad/Sketcher/App/planegcs/GCS.cpp
    "$here"/freecad/Sketcher/App/planegcs/SubSystem.cpp
    "$here"/freecad/Sketcher/App/planegcs/Constraints.cpp
    "$here"/freecad/Sketcher/App/planegcs/Geo.cpp
    "$here"/freecad/Sketcher/App/planegcs/qp_eq.cpp
    "$here"/sketch.cpp
    "$here"/api.cpp
)
includes=(-I "$here/shim" -I "$here" -I "$eigen" -I "$boost")
# Eigen's own asserts are left on as in FreeCAD's release build (NDEBUG is set there too).
common=(-std=c++23 -O2 -DNDEBUG -DEIGEN_MPL2_ONLY -w)

build_native() {
    local cxx="${CXX:-c++}" out="$here/build" lib
    case "$(uname -s)" in
        Darwin) lib=libplanegcs.dylib ;;
        *) lib=libplanegcs.so ;;
    esac
    mkdir -p "$out/obj"
    local objs=() pids=()
    for src in "${sources[@]}"; do
        local obj="$out/obj/$(basename "${src%.cpp}").o"
        objs+=("$obj")
        "$cxx" "${common[@]}" -fPIC "${includes[@]}" -c "$src" -o "$obj" &
        pids+=($!)
    done
    for pid in "${pids[@]}"; do wait "$pid"; done
    "$cxx" -shared -o "$out/$lib" "${objs[@]}"
    echo "built $out/$lib"
}

build_wasm() {
    if ! command -v emcc >/dev/null; then
        if [[ -n "$emsdk" && -f "$emsdk/emsdk_env.sh" ]]; then
            # shellcheck disable=SC1091
            source "$emsdk/emsdk_env.sh" >/dev/null 2>&1
        fi
    fi
    if ! command -v emcc >/dev/null; then
        echo "build.sh: emcc not found: set EMSDK (or PLANEGCS_TOOLCHAIN) to an activated emsdk" >&2
        exit 2
    fi
    local out="$here/dist" tmp
    tmp="$(mktemp -d)"
    mkdir -p "$out"
    local objs=() pids=()
    for src in "${sources[@]}"; do
        local obj="$tmp/$(basename "${src%.cpp}").o"
        objs+=("$obj")
        local extra=()
        if [[ "$(basename "$src")" == GCS.cpp ]]; then extra=(-include "$here/shim/deferred_async.h"); fi
        emcc "${common[@]}" -fwasm-exceptions -msimd128 -msse3 "${includes[@]}" "${extra[@]}" -c "$src" -o "$obj" &
        pids+=($!)
    done
    for pid in "${pids[@]}"; do wait "$pid"; done
    emcc -O2 -fwasm-exceptions "${objs[@]}" -o "$out/planegcs.mjs" \
        -sMODULARIZE=1 -sEXPORT_ES6=1 -sEXPORT_NAME=createPlaneGCS \
        -sENVIRONMENT=web,worker,node \
        -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=1048576 \
        -sEXPORTED_FUNCTIONS=_pgcs_version,_pgcs_solve,_pgcs_new,_pgcs_last_error,_pgcs_free,_pgcs_handle_solve,_pgcs_result,_pgcs_move_geometry,_pgcs_init_move,_pgcs_move,_pgcs_end_move,_malloc,_free \
        -sEXPORTED_RUNTIME_METHODS=ccall,cwrap,UTF8ToString
    rm -rf "$tmp"
    ls -l "$out"/planegcs.mjs "$out"/planegcs.wasm
}

case "$target" in
    native) build_native ;;
    wasm) build_wasm ;;
    all) build_native; build_wasm ;;
    *) echo "usage: build.sh [native|wasm|all]" >&2; exit 2 ;;
esac
