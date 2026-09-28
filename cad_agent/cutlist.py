"""Cut list: what to order and cut, derived from the parts, never typed.

A part module opts in by exposing CUTLIST, a list of dicts with `kind`
(extrusion profile, panel, fastener), `length_mm` or `size_mm`, and `qty`.
"""
from __future__ import annotations
from collections import defaultdict
from .state import part_names, build_part, project_dir
import importlib.util

# Rough vendor prices, September 2026, from the tooling survey. Planning only.
PRICE = {
    "2020": 3.60 / 1000.0,   # $/mm
    "2040": 5.80 / 1000.0,
    "4040": 10.00 / 1000.0,
    "acrylic_3mm": 0.00004,  # $/mm^2
    "M3": 0.05, "M4": 0.07, "M5": 0.09,
}


def cutlist(slug: str) -> dict:
    rows = defaultdict(lambda: {"qty": 0, "total_mm": 0.0})
    for name in part_names(slug):
        path = project_dir(slug) / "parts" / f"{name}.py"
        spec = importlib.util.spec_from_file_location(f"_cut_{name}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for item in getattr(mod, "CUTLIST", []):
            key = (item["kind"], item.get("length_mm"))
            rows[key]["qty"] += int(item.get("qty", 1))
            rows[key]["total_mm"] += float(item.get("length_mm") or 0) * int(item.get("qty", 1))

    out = []
    total = 0.0
    for (kind, length), agg in sorted(rows.items(), key=lambda kv: str(kv[0])):
        unit = PRICE.get(kind)
        cost = round(agg["total_mm"] * unit, 2) if unit and length else (
            round(agg["qty"] * unit, 2) if unit else None)
        if cost:
            total += cost
        out.append({"kind": kind, "length_mm": length, "qty": agg["qty"],
                    "total_mm": round(agg["total_mm"], 1), "cost_usd": cost})
    return {"rows": out, "total_usd": round(total, 2),
            "note": "prices are rough planning figures from the Sept 2026 tooling survey"}
