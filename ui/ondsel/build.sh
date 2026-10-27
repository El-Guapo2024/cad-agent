#!/usr/bin/env bash
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Builds the Assembly solver: OndselSolver (ui/ondsel/upstream, FreeCAD's submodule at 4be80eef02a3,
# unchanged) and the port of AssemblyObject.cpp's mapping onto it (assembly.cpp + api.cpp):
#
#   ui/ondsel/build.sh native   ->  ui/ondsel/build/libondsel.so (.dylib on macOS), which
#                                   cad_agent/ondsel.py loads through ctypes
#   ui/ondsel/build.sh wasm     ->  ui/ondsel/dist/ondsel.mjs + ondsel.wasm (ES module, no pthreads),
#                                   which ui/src/ondsel.ts loads; committed
#   ui/ondsel/build.sh all      ->  both
#
# OndselSolver needs nothing but a C++17 compiler (it is built here as C++20, for the port's
# std::map::contains). For wasm, Emscripten: EMSDK (an activated emsdk; 4.0.10 built dist/), or emcc on
# PATH, or PLANEGCS_TOOLCHAIN holding emsdk/ (the Sketcher solver's toolchain folder).
# CXX picks the native compiler (default c++); JOBS how many compile at once (default 4).
#
# The source list is OndselSolver/CMakeLists.txt's, read from it, so the library is the one FreeCAD
# links; FreeCAD builds it with -O2 (CMAKE_BUILD_TYPE Release adds -O3; the weekly AppImage is built
# with RelWithDebInfo, -O2), as here.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
target="${1:-native}"
up="$here/upstream"
tc="${PLANEGCS_TOOLCHAIN:-}"
emsdk="${EMSDK:-${tc:+$tc/emsdk}}"
jobs="${JOBS:-4}"

mapfile -t upstream_sources < <(grep -oE '\b[A-Za-z0-9_]+\.cpp\b' "$up/OndselSolver/CMakeLists.txt" | sort -u)
sources=()
for s in "${upstream_sources[@]}"; do sources+=("$up/OndselSolver/$s"); done
sources+=("$here/assembly.cpp" "$here/api.cpp")
includes=(-I "$up" -I "$up/OndselSolver" -I "$here")
common=(-std=c++20 -O2 -DNDEBUG -w)

compile_all() {   # compile_all <compiler> <objdir> <flags...>
    local cc="$1" objdir="$2"; shift 2
    mkdir -p "$objdir"
    # an object is rebuilt when its source, or for the port's two files the port's headers, are newer
    printf '%s\n' "${sources[@]}" | xargs -P "$jobs" -I{} sh -c '
        src="$1"; shift; cc="$1"; shift; objdir="$1"; shift; here="$1"; shift
        obj="$objdir/$(basename "${src%.cpp}").o"
        stale=0
        if [ ! -f "$obj" ] || [ "$src" -nt "$obj" ]; then stale=1; fi
        case "$src" in "$here"/*) for h in "$here/assembly.h" "$here/json.h"; do [ "$h" -nt "$obj" ] && stale=1; done ;; esac
        if [ "$stale" = 1 ]; then "$cc" "$@" -c "$src" -o "$obj"; fi
    ' _ {} "$cc" "$objdir" "$here" "$@"
}

objects() {   # objects <objdir>
    for s in "${sources[@]}"; do echo "$1/$(basename "${s%.cpp}").o"; done
}

build_native() {
    local cxx="${CXX:-c++}" out="$here/build" lib
    case "$(uname -s)" in
        Darwin) lib=libondsel.dylib ;;
        *) lib=libondsel.so ;;
    esac
    compile_all "$cxx" "$out/obj" "${common[@]}" -fPIC "${includes[@]}"
    mapfile -t objs < <(objects "$out/obj")
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
    local out="$here/dist" objdir="$here/build/wasm-obj"
    mkdir -p "$out"
    compile_all emcc "$objdir" "${common[@]}" -fwasm-exceptions "${includes[@]}"
    mapfile -t objs < <(objects "$objdir")
    emcc -O2 -fwasm-exceptions "${objs[@]}" -o "$out/ondsel.mjs" \
        -sMODULARIZE=1 -sEXPORT_ES6=1 -sEXPORT_NAME=createOndsel \
        -sENVIRONMENT=web,worker,node \
        -sALLOW_MEMORY_GROWTH=1 -sSTACK_SIZE=4194304 \
        -sEXPORTED_FUNCTIONS=_ondsel_version,_ondsel_solve,_ondsel_export,_ondsel_query,_ondsel_new,_ondsel_last_error,_ondsel_free,_ondsel_handle_solve,_ondsel_pre_drag,_ondsel_drag_step,_ondsel_rigid_step,_ondsel_simulate,_ondsel_post_drag,_malloc,_free \
        -sEXPORTED_RUNTIME_METHODS=ccall,cwrap,UTF8ToString
    ls -l "$out"/ondsel.mjs "$out"/ondsel.wasm
}

case "$target" in
    native) build_native ;;
    wasm) build_wasm ;;
    all) build_native; build_wasm ;;
    *) echo "usage: build.sh [native|wasm|all]" >&2; exit 2 ;;
esac
