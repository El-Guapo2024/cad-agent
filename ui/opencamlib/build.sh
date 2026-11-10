#!/usr/bin/env bash
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Builds OpenCamLib (https://github.com/aewallin/opencamlib, LGPL-2.1-or-later), the library FreeCAD's CAM Surface and
# Waterline operations import as `ocl`, as a Python module, from its release 2022.12.18 unchanged: the version FreeCAD's
# AppImage (weekly-2026.09.30) ships in usr/lib/python3.13/site-packages/opencamlib, so the ops cut what freecadcmd cuts.
#
#   ui/opencamlib/build.sh  ->  ui/opencamlib/build/ocl<EXT_SUFFIX>, which cad_agent/cam_runtime.py puts on sys.path
#
# The source is fetched once (OCL_SRC: an unpacked copy instead) and checked against its sha256. The sources and flags
# are those of OpenCamLib's src/CMakeLists.txt and src/pythonlib/pythonlib.cmake (C++14, OpenMP, Boost.Python); CMake
# is not needed. Boost.Python is compiled into the module from its own sources (boostorg/python at the tag of the Boost
# headers found, 1.83.0 checked by sha256; BOOST_PYTHON_SRC: an unpacked copy instead), statically as OpenCamLib's
# CMake links it, so any Python works, not only the one a distribution built Boost.Python for. Needs a C++ compiler,
# Boost's headers (Ubuntu: libboost-dev; BOOST_INCLUDE) and the Python headers of the Python that will import it.
# PYTHON picks the Python (default .venv/bin/python, then python3); CXX the compiler; JOBS how many compile at once.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../.." && pwd)"
version="2022.12.18"
sha="24698fb937c66905f53c99d399e60623b9555f6d04a0fb3609b248a7c31c9c63"
bp_sha_1_83_0="6702cecd9759b155e76fc19998fb6e907c115515f82eae80704b9a3521099e3f"
jobs="${JOBS:-4}"
cxx="${CXX:-c++}"
out="$here/build"
obj="$out/obj"

py="${PYTHON:-}"
if [[ -z "$py" ]]; then
    if [[ -x "$root/.venv/bin/python" ]]; then py="$root/.venv/bin/python"; else py="$(command -v python3)"; fi
fi
ext="$("$py" -c 'import sysconfig; print(sysconfig.get_config_var("EXT_SUFFIX"))')"
pyinc="${PYTHON_INCLUDE:-$("$py" -c 'import sysconfig; print(sysconfig.get_paths()["include"])')}"
if [[ ! -f "$pyinc/Python.h" ]]; then
    echo "build.sh: no Python.h in $pyinc: set PYTHON_INCLUDE to the headers of $py" >&2
    exit 2
fi

src="${OCL_SRC:-}"
if [[ -z "$src" ]]; then
    src="$out/opencamlib-$version"
    if [[ ! -d "$src" ]]; then
        mkdir -p "$out"
        tgz="$out/opencamlib-$version.tar.gz"
        curl -sfL -o "$tgz" "https://github.com/aewallin/opencamlib/archive/refs/tags/$version.tar.gz"
        echo "$sha  $tgz" | sha256sum -c --quiet -
        tar xzf "$tgz" -C "$out"
        rm "$tgz"
    fi
fi
s="$src/src"

boostinc="${BOOST_INCLUDE:-/usr/include}"
bver="$(sed -n 's/^#define BOOST_LIB_VERSION "\(.*\)"/\1/p' "$boostinc/boost/version.hpp" 2>/dev/null || true)"
if [[ -z "$bver" || ! -f "$boostinc/boost/python.hpp" ]]; then
    echo "build.sh: no Boost headers with boost/python.hpp in $boostinc: install libboost-dev or set BOOST_INCLUDE" >&2
    exit 2
fi
bdot="${bver//_/.}"; [[ "$bdot" == *.*.* ]] || bdot="$bdot.0"
bp="${BOOST_PYTHON_SRC:-}"
if [[ -z "$bp" ]]; then
    bp="$out/python-boost-$bdot"
    if [[ ! -d "$bp" ]]; then
        tgz="$out/boost-python-$bdot.tar.gz"
        curl -sfL -o "$tgz" "https://github.com/boostorg/python/archive/refs/tags/boost-$bdot.tar.gz"
        if [[ "$bdot" == "1.83.0" ]]; then echo "$bp_sha_1_83_0  $tgz" | sha256sum -c --quiet -; fi
        tar xzf "$tgz" -C "$out"
        rm "$tgz"
    fi
fi

mkdir -p "$out/obj"
# src/version_string.cmake writes this from `git describe`; the release's tag is the version
printf '#define VERSION_STRING "%s"\n' "$version" > "$out/obj/version_string.hpp"

sources=(ocl.cpp
    geo/arc.cpp geo/bbox.cpp geo/ccpoint.cpp geo/clpoint.cpp geo/line.cpp geo/path.cpp geo/point.cpp geo/stlreader.cpp
    geo/stlsurf.cpp geo/triangle.cpp
    cutters/ballcutter.cpp cutters/bullcutter.cpp cutters/compositecutter.cpp cutters/conecutter.cpp cutters/cylcutter.cpp
    cutters/ellipse.cpp cutters/ellipseposition.cpp cutters/millingcutter.cpp
    dropcutter/adaptivepathdropcutter.cpp dropcutter/batchdropcutter.cpp dropcutter/pathdropcutter.cpp
    dropcutter/pointdropcutter.cpp
    algo/adaptivewaterline.cpp algo/batchpushcutter.cpp algo/fiber.cpp algo/fiberpushcutter.cpp algo/interval.cpp
    algo/simple_weave.cpp algo/smart_weave.cpp algo/waterline.cpp algo/weave.cpp
    common/lineclfilter.cpp common/numeric.cpp
    pythonlib/ocl_cutters.cpp pythonlib/ocl_geometry.cpp pythonlib/ocl_algo.cpp pythonlib/ocl_dropcutter.cpp pythonlib/ocl.cpp)
# Boost.Python's libs/python/src (its build's source list, numpy left out)
bpsources=(dict.cpp errors.cpp exec.cpp import.cpp list.cpp long.cpp module.cpp object_operators.cpp object_protocol.cpp
    slice.cpp str.cpp tuple.cpp wrapper.cpp
    converter/arg_to_python_base.cpp converter/builtin_converters.cpp converter/from_python.cpp converter/registry.cpp
    converter/type_id.cpp
    object/class.cpp object/enum.cpp object/function.cpp object/function_doc_signature.cpp object/inheritance.cpp
    object/iterator.cpp object/life_support.cpp object/pickle_support.cpp object/stl_iterator.cpp)
common=(-O2 -fPIC -DNDEBUG -DBOOST_PYTHON_STATIC_LIB -w -I "$boostinc" -I "$pyinc")
flags=(-std=c++14 -fopenmp -Wno-deprecated "${common[@]}"
    -I "$obj" -I "$s" -I "$s/cutters" -I "$s/geo" -I "$s/algo" -I "$s/dropcutter" -I "$s/common")
bpflags=(-std=c++14 -DBOOST_PYTHON_SOURCE "${common[@]}")

# objects are per Python (its headers decide Boost.Python's code): a build for another Python starts over
tag="$("$py" -c 'import sys; print(sys.implementation.cache_tag)')"
obj="$obj/$tag"
mkdir -p "$obj"
cp "$out/obj/version_string.hpp" "$obj/"
objs=()
for f in "${sources[@]}"; do objs+=("$obj/ocl_${f//\//_}.o"); done
for f in "${bpsources[@]}"; do objs+=("$obj/bp_${f//\//_}.o"); done
{
    for f in "${sources[@]}"; do
        o="$obj/ocl_${f//\//_}.o"
        if [[ ! -f "$o" ]]; then echo "$cxx ${flags[*]} -c $s/$f -o $o"; fi
    done
    for f in "${bpsources[@]}"; do
        o="$obj/bp_${f//\//_}.o"
        if [[ ! -f "$o" ]]; then echo "$cxx ${bpflags[*]} -c $bp/src/$f -o $o"; fi
    done
} | xargs -P "$jobs" -I{} sh -c '{}'

"$cxx" -shared -fopenmp -o "$out/ocl$ext" "${objs[@]}"
"$py" -c "import sys; sys.path.insert(0, '$out'); import ocl; print('built', ocl.__file__, ocl.version())"
