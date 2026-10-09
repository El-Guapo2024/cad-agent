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
  # uv keeps what an interpreter reported and believes it until told to ask again. A record made without
  # SYSTEM_VERSION_COMPAT=0 (by any uv command run in a shell that lacked it) says macOS 10.16 and outlives
  # this export, and uv then turns down every macosx_11_0 or newer wheel: embreex's macosx_13_0 one, so
  # the extra fails to resolve. Any --refresh option makes uv ask the interpreter again; naming one
  # package keeps that to a single index lookup, where --no-cache fetches everything again.
  if command -v uv >/dev/null 2>&1; then
    uv venv -q --python ">=3.12" "$venv" >&2
    uv pip install -q --refresh-package cad-agent -p "$venv/bin/python" -e "$pkg" >&2
    uv pip install -q --refresh-package embreex -p "$venv/bin/python" -e "$root[embree]" >&2 || no_embree
  else
    py=""
    for c in python3.13 python3.12 python3; do
      if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 12))'; then py="$c"; break; fi
    done
    [ -n "$py" ] || { echo "cad-agent: needs Python 3.12 or newer (or uv: https://docs.astral.sh/uv/)" >&2; exit 0; }
    "$py" -m venv "$venv" >&2
    "$venv/bin/pip" install -q -e "$pkg" >&2
    "$venv/bin/pip" install -q -e "$root[embree]" >&2 || no_embree
  fi
  echo "$want" > "$data/installed"
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
