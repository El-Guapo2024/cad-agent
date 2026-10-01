"""PARAMS in a part module, read and edited in place.

`cad set` and the workbench's parameter fields change a part's dimensions by
rewriting exactly one literal in its PARAMS dict. Comments, order and layout
stay as they were, so git shows a one-number diff and the Python remains the
source of truth: a value set here is a value in the code.

A value the file computes (an expression, not a literal) is shown but not
editable: rewriting it would throw away what the expression meant.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

EDITABLE = (bool, int, float, str)


class ParamError(ValueError):
    """A value that PARAMS cannot take, or a PARAMS this can't edit safely."""


def _dict_node(tree: ast.Module):
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PARAMS"
                                                for t in node.targets):
            return node.value
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                and node.target.id == "PARAMS":
            return node.value
    return None


def _entries(src: str):
    node = _dict_node(ast.parse(src))
    if not isinstance(node, ast.Dict):
        return []
    return [(k.value, v) for k, v in zip(node.keys, node.values)
            if isinstance(k, ast.Constant) and isinstance(k.value, str)]


def read(path: Path) -> dict:
    """{name: {"value", "type", "editable"}}, in file order."""
    src = Path(path).read_text()
    out = {}
    for name, node in _entries(src):
        try:
            value = ast.literal_eval(node)
            ok = isinstance(value, EDITABLE)
        except ValueError:
            value, ok = ast.get_source_segment(src, node), False
        out[name] = {"value": value, "type": type(value).__name__ if ok else "expression",
                     "editable": ok}
    return out


def coerce(name: str, old, new):
    """The new value in the old value's type: 8 for a float becomes 8.0,
    and a whole-number parameter refuses 2.5."""
    if isinstance(old, bool):
        if isinstance(new, bool):
            return new
        if isinstance(new, str) and new.lower() in ("true", "false"):
            return new.lower() == "true"
        raise ParamError(f"{name} is true or false, not {new!r}")
    if isinstance(old, int):
        if isinstance(new, (int, float)) and not isinstance(new, bool) and float(new).is_integer():
            return int(new)
        raise ParamError(f"{name} is a whole number, not {new!r}")
    if isinstance(old, float):
        if isinstance(new, (int, float)) and not isinstance(new, bool):
            return float(new)
        raise ParamError(f"{name} is a number, not {new!r}")
    return str(new)


def _literal(value) -> str:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        return repr(round(value, 6))
    if isinstance(value, int):
        return str(value)
    return json.dumps(value)          # "M3", as the files write them


def write(path: Path, changes: dict) -> None:
    """Replace each named literal in place. ast offsets are UTF-8 byte
    columns, so the edit happens on bytes, last span first."""
    path = Path(path)
    raw = path.read_bytes()
    src = raw.decode()
    starts = [0]
    for line in raw.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    spans = []
    for name, node in _entries(src):
        if name in changes:
            a = starts[node.lineno - 1] + node.col_offset
            b = starts[node.end_lineno - 1] + node.end_col_offset
            spans.append((a, b, _literal(changes[name]).encode()))
    missing = sorted(set(changes) - {n for n, _ in _entries(src)})
    if missing:
        raise ParamError(f"PARAMS has no {', '.join(missing)}")
    for a, b, text in sorted(spans, reverse=True):
        raw = raw[:a] + text + raw[b:]
    after = read_src(raw.decode())
    for name, value in changes.items():             # the file now says what was asked
        if after.get(name) != value:
            raise ParamError(f"rewriting {name} did not take; the file is unchanged")
    path.write_bytes(raw)


def read_src(src: str) -> dict:
    out = {}
    for name, node in _entries(src):
        try:
            out[name] = ast.literal_eval(node)
        except ValueError:
            pass
    return out
