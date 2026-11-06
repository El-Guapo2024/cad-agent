#!/usr/bin/env bash
# Builds the three native solvers a plugin install needs and the wheels can't carry, from the plugin's own sources:
# the Sketcher's PlaneGCS (ui/planegcs), the Assembly's OndselSolver (ui/ondsel) and the CAM workbench's libarea
# (ui/libarea). Without them every sketch, assembly and CAM op says its solver is not built. install.sh starts this
# in the background once per plugin version; the output goes to $data/natives.log.
#   natives.sh ROOT DATA VENV_PYTHON
# Needs a C++ compiler. Eigen 5.0.0 (FreeCAD's) and pybind11 are fetched into DATA/toolchain; Boost's headers are
# the system's (apt install libboost-dev, brew install boost) or else fetched there too (126 MB, once).
set -uo pipefail
root="$1" data="$2" py="$3"
tc="$data/toolchain"
mkdir -p "$tc"
say() { echo "cad-agent natives: $*"; }
cxx="${CXX:-c++}"
command -v "$cxx" >/dev/null 2>&1 || { say "no C++ compiler ($cxx): sketches, assemblies and CAM need one (xcode-select --install, or apt install g++)"; exit 1; }
fetch() {   # URL DIR: unpack a tarball into the toolchain folder once
  [ -d "$tc/$2" ] && return 0
  say "fetching $1"
  case "$1" in *.bz2) z=j ;; *) z=z ;; esac
  curl -sfL "$1" | tar x${z}f - -C "$tc" ${3:+"$3"} && [ -d "$tc/$2" ]
}
fetch https://gitlab.com/libeigen/eigen/-/archive/5.0.0/eigen-5.0.0.tar.gz eigen-5.0.0 || say "could not fetch Eigen 5.0.0"
boost=""
for d in /usr/include /opt/homebrew/include /usr/local/include; do [ -z "$boost" ] && [ -d "$d/boost/graph" ] && boost="$d"; done
if [ -z "$boost" ]; then
  fetch https://archives.boost.io/release/1.86.0/source/boost_1_86_0.tar.bz2 boost_1_86_0 boost_1_86_0/boost \
    && boost="$tc/boost_1_86_0" || say "could not fetch Boost's headers"
fi
"$py" -m pip --version >/dev/null 2>&1 && "$py" -m pip install -q pybind11 \
  || { command -v uv >/dev/null 2>&1 && uv pip install -q -p "$py" pybind11; } || say "could not install pybind11"
# libarea's modules need the headers of the venv's Python; a system Python often has none (python3-dev). A
# uv-managed Python of the same minor version carries them, and a module built against those imports here.
pyinc="$("$py" -c 'import sysconfig; print(sysconfig.get_paths()["include"])')"
if [ ! -f "$pyinc/Python.h" ] && command -v uv >/dev/null 2>&1; then
  minor="$("$py" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
  managed="$(uv python find --python-preference only-managed "$minor" 2>/dev/null \
    || { uv python install -q "$minor" >/dev/null 2>&1 && uv python find --python-preference only-managed "$minor"; })"
  inc="$([ -n "$managed" ] && "$managed" -c 'import sysconfig; print(sysconfig.get_paths()["include"])')"
  if [ -f "$inc/Python.h" ]; then export PYTHON_INCLUDE="$inc"; say "Python $minor headers from $managed"; fi
fi
[ -f "${PYTHON_INCLUDE:-$pyinc}/Python.h" ] || say "no Python.h for $py: CAM needs the Python headers (apt install python3-dev)"
rc=0
run() {   # NAME: one solver's build.sh native
  s=$(date +%s)
  if EIGEN_DIR="$tc/eigen-5.0.0" BOOST_DIR="$boost" PYTHON="$py" JOBS="${JOBS:-4}" bash "$root/ui/$1/build.sh" native; then
    say "$1 built in $(( $(date +%s) - s )) s"
  else
    say "$1 did not build (see above)"; rc=1
  fi
}
run planegcs
run ondsel
run libarea
exit $rc
