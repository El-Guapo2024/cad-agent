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
  if command -v uv >/dev/null 2>&1; then
    uv venv -q --python ">=3.12" "$venv" >&2
    uv pip install -q -p "$venv/bin/python" -e "$root" >&2
  else
    py=""
    for c in python3.13 python3.12 python3; do
      if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 12))'; then py="$c"; break; fi
    done
    [ -n "$py" ] || { echo "cad-agent: needs Python 3.12 or newer (or uv: https://docs.astral.sh/uv/)" >&2; exit 0; }
    "$py" -m venv "$venv" >&2
    "$venv/bin/pip" install -q -e "$root" >&2
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
