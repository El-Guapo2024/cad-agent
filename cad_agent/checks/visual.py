"""Visual checks: what the render shows, compared with what it showed before.

Two faults on the first rover were layout errors a person spotted by looking.
The in-plane gate now catches that class numerically, but "looking" stays
valuable for a reason no numeric rule replaces: it notices changes nobody
thought to write a rule about.

So the render becomes a checkable artifact. Approve an image once, and every
later run compares against it and reports what moved. That is the fast part
of the loop: change a parameter and the run tells you which views changed and
by how much, instead of you flicking between pictures.

Three rules come out of the same pair of images:

  silhouette   the fraction of the frame the part covers. Near zero means
               nothing was drawn, which is how a broken build looks when the
               solid is empty but the render still succeeds.
  drift        the fraction of pixels that differ from the approved image.
               Deliberate changes are approved; accidental ones are caught.
  bbox shift   whether the drawn extent moved, which separates "the part
               changed shape" from "the part moved in frame".

A diff image is written for any drift, with changed pixels marked, so the
result is something to open rather than a percentage to trust.

Tolerances exist because rasterisation is not exact at silhouette edges. A
pixel counts as changed only past a channel difference, and drift is only a
failure past a fraction of the frame; both are stated in every row.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ..registry import Row
from ..render import VIEWS, draw, read_png, tessellate

# A pixel differs when any channel moves by more than this. Anti-aliasing and
# the two rasterisers' edge coverage account for a few levels on their own.
CHANNEL_TOL = 24

# Below this fraction of changed pixels a render counts as unchanged.
DRIFT_TOL = 0.002        # 0.2% of the frame

# Below this coverage nothing meaningful was drawn.
MIN_COVERAGE = 0.005     # 0.5% of the frame

DEFAULT_VIEWS = ("iso",)
SIZE = (640, 480)        # smaller than a report render; comparison, not display


def baseline_dir(project_dir: Path) -> Path:
    d = Path(project_dir) / "baseline"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _coverage(img: np.ndarray) -> float:
    """Fraction of the frame that is not background.

    Background is taken from the corner pixel rather than a constant, so a
    theme or palette change does not read as the part vanishing.
    """
    bg = img[0, 0].astype(int)
    d = np.abs(img.astype(int) - bg).max(axis=2)
    return float((d > CHANNEL_TOL).mean())


def _drawn_bbox(img: np.ndarray):
    bg = img[0, 0].astype(int)
    mask = np.abs(img.astype(int) - bg).max(axis=2) > CHANNEL_TOL
    if not mask.any():
        return None
    ys, xs = np.nonzero(mask)
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def _write_diff(base: np.ndarray, cur: np.ndarray, mask: np.ndarray, path: Path):
    """Approved image dimmed, with everything that changed marked in red."""
    from ..render import _write_png
    out = (cur.astype(float) * 0.35 + 255 * 0.28).astype(np.uint8)
    out[mask] = np.array([214, 48, 32], dtype=np.uint8)
    _write_png(np.ascontiguousarray(out), path)


def compare(current_png: Path, baseline_png: Path, diff_png: Path) -> dict:
    """Compare two renders. Returns coverage, drift and where it moved."""
    cur = read_png(current_png)
    base = read_png(baseline_png)
    if cur.shape != base.shape:
        return {"state": "SIZE_CHANGED",
                "note": f"render is {cur.shape[1]}x{cur.shape[0]}, approved "
                        f"image is {base.shape[1]}x{base.shape[0]}"}
    d = np.abs(cur.astype(int) - base.astype(int)).max(axis=2)
    mask = d > CHANNEL_TOL
    drift = float(mask.mean())
    res = {"state": "COMPARED", "drift": drift,
           "coverage": _coverage(cur),
           "baseline_coverage": _coverage(base),
           "bbox": _drawn_bbox(cur), "baseline_bbox": _drawn_bbox(base)}
    if drift > 0:
        _write_diff(base, cur, mask, diff_png)
        res["diff_png"] = str(diff_png)
        ys, xs = np.nonzero(mask)
        res["changed_region"] = [int(xs.min()), int(ys.min()),
                                 int(xs.max()), int(ys.max())]
    return res


def render_for_check(solid, out_dir: Path, name: str, view: str) -> Path:
    mesh = tessellate(solid, 0.05, 0.25)
    return draw(mesh, Path(out_dir) / f"_check_{name}_{view}.png",
                view=view, size=SIZE)


def visual_rows(subject: str, solid, out_dir: Path, project_dir: Path,
                views=DEFAULT_VIEWS):
    """The three visual rules, per view, for one subject."""
    bdir = baseline_dir(project_dir)
    for view in views:
        if view not in VIEWS:
            yield Row(subject=subject, rule=f"visual/{view}", state="UNCHECKED",
                      measured=f"unknown view {view!r}",
                      limit=f"one of {sorted(VIEWS)}",
                      source="the part declared a view the renderer has no basis for")
            continue

        cur = render_for_check(solid, out_dir, subject, view)
        cov = _coverage(read_png(cur))

        yield Row(subject=subject, rule=f"silhouette/{view}",
                  state="PASS" if cov >= MIN_COVERAGE else "FAIL",
                  measured=f"{cov * 100:.2f}% of the frame",
                  limit=f"at least {MIN_COVERAGE * 100:.1f}%",
                  source="non-background pixels; near zero means nothing was drawn",
                  artifacts=[str(cur)])

        base = bdir / f"{subject}_{view}.png"
        if not base.exists():
            yield Row(subject=subject, rule=f"drift/{view}", state="UNCHECKED",
                      measured="no approved image",
                      limit=f"drift under {DRIFT_TOL * 100:.1f}% of the frame",
                      source="look at the render, then `cad approve` makes it the baseline this view is gated on",
                      artifacts=[str(cur)])
            continue

        r = compare(cur, base, Path(out_dir) / f"_diff_{subject}_{view}.png")
        if r["state"] == "SIZE_CHANGED":
            yield Row(subject=subject, rule=f"drift/{view}", state="UNCHECKED",
                      measured=r["note"], limit="same size as the approved image",
                      source="re-approve the view at the new size")
            continue

        drift = r["drift"]
        arts = [str(cur), str(base)] + ([r["diff_png"]] if "diff_png" in r else [])
        where = ""
        if "changed_region" in r:
            x0, y0, x1, y1 = r["changed_region"]
            where = f", changed region x {x0}–{x1}, y {y0}–{y1}"
        yield Row(subject=subject, rule=f"drift/{view}",
                  state="PASS" if drift <= DRIFT_TOL else "FAIL",
                  measured=f"{drift * 100:.3f}% of pixels differ{where}",
                  limit=f"{DRIFT_TOL * 100:.1f}% at a channel tolerance of {CHANNEL_TOL}",
                  source="compared against the approved image; a deliberate "
                         "change is re-approved, an accidental one is caught",
                  artifacts=arts)

        if r["bbox"] and r["baseline_bbox"]:
            moved = max(abs(a - b) for a, b in zip(r["bbox"], r["baseline_bbox"]))
            yield Row(subject=subject, rule=f"extent/{view}",
                      state="PASS" if moved <= 1 else "FAIL",
                      measured=f"drawn extent moved {moved} px",
                      limit="1 px",
                      source="separates a change of shape from a change of "
                             "position or scale in the frame")


def approve(project_dir: Path, out_dir: Path, subject: str, view: str) -> Path:
    """Promote the current render of one view to the approved image."""
    src = Path(out_dir) / f"_check_{subject}_{view}.png"
    if not src.exists():
        raise FileNotFoundError(
            f"no render to approve at {src}; run the checks first so there is "
            "something to look at before approving it")
    dest = baseline_dir(project_dir) / f"{subject}_{view}.png"
    dest.write_bytes(src.read_bytes())
    return dest
