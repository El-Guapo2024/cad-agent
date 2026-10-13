#!/bin/sh
# Claude Code plugin, SessionStart: install the cad CLI (and its CAD kernel) once per plugin
# version into the plugin's data folder, and put `cad` on PATH for the session.
# Designs go to <your project>/cad-projects (CAD_PROJECTS), never into the plugin's own folder.
set -eu
root="${CLAUDE_PLUGIN_ROOT:?run by Claude Code as a plugin hook}"
data="${CLAUDE_PLUGIN_DATA:-$HOME/.claude/plugins/data/cad-agent}"
venv="$data/venv"
want="$(sed -n 's/^version = "\(.*\)"/\1/p' "$root/pyproject.toml" | head -1) $root"
mkdir -p "$data/bin"
fresh=""
if [ ! -x "$venv/bin/python" ] || [ "$(cat "$data/installed" 2>/dev/null)" != "$want" ]; then
  echo "cad-agent: installing the CAD kernel into $venv (first run only, a few minutes)" >&2
  rm -rf "$venv"
  # A Python built against an older macOS SDK (miniconda's, for one) says it runs macOS 10.16,
  # and uv then turns down the kernel's macosx_11_0 wheels. This makes macOS give the real
  # version, as pip asks for it.
  export SYSTEM_VERSION_COMPAT=0
  pkg="$root"
  [ "$(uname -s)" = Darwin ] && pkg="$root[metal]"   # renders through Metal (no headless OpenGL on a Mac)
  # Embree casts the wall-thickness rays some thirty times faster, with the same numbers. It is optional:
  # a platform it has no wheel for keeps trimesh's slower caster, so this step may fail without failing the install.
  no_embree() { echo "cad-agent: Embree not installed (optional); wall-thickness rays will use the slower Python caster" >&2; }
  # The ISO screw, nut and washer of the part library (`cad lib use iso4762-screw`) are drawn by bd_warehouse
  # (Apache-2.0): pure Python, under a megabyte on top of the build123d and bd_materials the kernel already has,
  # and a second or two. Optional like Embree, because a step that fails here (the network dropping) should cost
  # those three entries and not the install; `cad lib use` says they need it.
  no_fasteners() { echo "cad-agent: bd_warehouse not installed (optional); the library's ISO screw, nut and washer need it: install 'bd_warehouse>=0.3' into $venv" >&2; }
  # uv keeps what an interpreter reported and believes it until told to ask again. A record made without
  # SYSTEM_VERSION_COMPAT=0 (by any uv command run in a shell that lacked it) says macOS 10.16 and outlives
  # this export, and uv then turns down every macosx_11_0 or newer wheel: embreex's macosx_13_0 one, so
  # the extra fails to resolve. Any --refresh option makes uv ask the interpreter again; naming one
  # package keeps that to a single index lookup, where --no-cache fetches everything again.
  # The kernel's wheels stop at Python 3.14 (OCP has none for cp315, and build123d says <3.15), so the
  # interpreter is asked for in that range: a uv that knows 3.15 would pick it on a machine with no other
  # 3.12 or newer, and the install would not resolve.
  if command -v uv >/dev/null 2>&1; then
    uv venv -q --python ">=3.12,<3.15" "$venv" >&2
    uv pip install -q --refresh-package cad-agent -p "$venv/bin/python" -e "$pkg" >&2
    uv pip install -q --refresh-package embreex -p "$venv/bin/python" -e "$root[embree]" >&2 || no_embree
    uv pip install -q --refresh-package bd-warehouse -p "$venv/bin/python" -e "$root[fasteners]" >&2 || no_fasteners
  else
    py=""
    for c in python3.13 python3.12 python3.14 python3; do
      if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(not (3, 12) <= sys.version_info[:2] < (3, 15))'; then py="$c"; break; fi
    done
    [ -n "$py" ] || { echo "cad-agent: needs Python 3.12 to 3.14 (or uv: https://docs.astral.sh/uv/)" >&2; exit 0; }
    "$py" -m venv "$venv" >&2
    "$venv/bin/pip" install -q -e "$pkg" >&2
    "$venv/bin/pip" install -q -e "$root[embree]" >&2 || no_embree
    "$venv/bin/pip" install -q -e "$root[fasteners]" >&2 || no_fasteners
  fi
  echo "$want" > "$data/installed"
  fresh=1
fi
ln -sf "$root/bin/cad" "$data/bin/cad"
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  {
    echo "export CAD_PYTHON=\"$venv/bin/python\""
    echo "export PATH=\"$data/bin:\$PATH\""
    # Working in a checkout of cad-agent itself keeps its own projects/ folder.
    if [ -z "${CAD_PROJECTS:-}" ] && [ ! -d "${CLAUDE_PROJECT_DIR:-$PWD}/cad_agent" ]; then
      echo "export CAD_PROJECTS=\"${CLAUDE_PROJECT_DIR:-$PWD}/cad-projects\""
    fi
  } >> "$CLAUDE_ENV_FILE"
fi
if [ -n "$fresh" ]; then
  # The first import of a new venv is the slow one, and it would fall on the first `cad` call of the session.
  # Python compiles every module it has not seen, and macOS checks each native library the first time it is
  # loaded: minutes on a Mac where the new files carry a provenance tag, as files written under a Claude
  # app do, against seconds once that is done. The warm worker gives up waiting after four minutes and the
  # command then runs cold, a second import. So load the kernel here, where the status line says
  # "cad-agent setup", with bytecode caching on whatever the caller exports, and say whether it runs.
  # Last, with `cad` already on PATH: a hook cut short here loses nothing (the install above is marked
  # done). The output goes to stderr, as everything here does: the stdout of a hook reaches the model.
  echo "cad-agent: loading the CAD kernel once so the first command is quick (first run only)" >&2
  CAD_WARM=0 PYTHONDONTWRITEBYTECODE= "$venv/bin/python" -P -m cad_agent.warm --version >&2 \
    || echo "cad-agent: installed, but the CAD kernel did not start; run \`cad --version\` to see why" >&2
  PYTHONDONTWRITEBYTECODE= "$venv/bin/python" -P -c "import trimesh, embreex" >/dev/null 2>&1 || true
fi
