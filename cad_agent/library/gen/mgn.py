"""The HIWIN MGN miniature linear guide: the rail and the carriage, drawn as envelopes.

An envelope is what the gates need and nothing more: the space the part takes and where it bolts down. The rail is
its box with the counterbored holes the screws go through; the carriage is its box, with the channel the rail runs
in and the four tapped holes of its top face. There are no balls, end caps, seals, ball grooves or grease nipple,
because no source this was drawn from gives them, and a model with details nobody checked would only look more
exact than it is. So both are `geometry = "envelope"` in the catalog, and a stiffness rule does not read them.

The rail runs along x, centred on the origin, its top face at z = +height/2. The carriage is centred on its own box,
and in its frame the rail's top face is the plane z = 0 and the rail's base is `rail_height` below it: HIWIN's H is
measured from the rail's base to the carriage's top face and H1 from the base to its underside, so the carriage body
is H - H1 tall and stands H1 above the base.

The numbers are HIWIN's, in the catalog, from the MG series tables (GW-11-5-EN-2207-K, tables 3.79 and 3.81). The
hole count follows their note: a rail is cut to a length and made symmetrically (L = (n - 1) x P + E1 + E2, F 3.16)
with the most holes that leave E1 = E2 at least E1/2 min (note 2 under table 3.82), unless `holes` says another.
"""
from __future__ import annotations

from build123d import Box, Cylinder, Pos


def rail(width, height, pitch, counterbore_dia, counterbore_depth, hole_dia, end_min, length, holes=None):
    """MGNR..R: a `width` x `height` box `length` long with a counterbored hole every `pitch` mm.

    `end_min` is E1/2 min. `holes` is the number of holes; left out, it is the most a rail of this length takes.
    """
    n = holes if holes is not None else int((length - 2 * end_min) // pitch) + 1
    if n < 1:
        raise ValueError(f"a rail {length:g} mm long has no room for a mounting hole ({end_min:g} mm from each end, "
                         f"{pitch:g} mm apart)")
    end = (length - (n - 1) * pitch) / 2.0
    body = Box(length, width, height)
    for i in range(n):
        x = -length / 2.0 + end + i * pitch
        body -= Pos(x, 0, 0) * Cylinder(hole_dia / 2.0, height + 2.0)
        body -= Pos(x, 0, height / 2.0 - counterbore_depth / 2.0 + 0.5) * Cylinder(counterbore_dia / 2.0,
                                                                                    counterbore_depth + 1.0)
    return body


def carriage(length, width, height, base_gap, rail_width, hole_pitch_along, hole_pitch_across, tap_dia, tap_depth,
             rail_gap=0.2):
    """MGN..C / MGN..H: a box `length` x `width` x (`height` - `base_gap`) with the rail's channel and four tapped holes.

    `rail_gap` is what the channel clears the rail by on each side and above. A real carriage runs preloaded on its
    rail, so this is not a dimension of it: it is what keeps the two from touching in every fit query.
    """
    body_height = height - base_gap
    body = Box(length, width, body_height)
    channel_top = rail_gap                  # the rail's top is z = 0 in this frame
    channel = Pos(0, 0, (-body_height / 2.0 - 1.0 + channel_top) / 2.0) \
        * Box(length + 2.0, rail_width + 2 * rail_gap, channel_top + body_height / 2.0 + 1.0)
    body -= channel
    for sx in (-1, 1):
        for sy in (-1, 1):
            body -= Pos(sx * (hole_pitch_along / 2.0), sy * (hole_pitch_across / 2.0),
                        body_height / 2.0 - tap_depth / 2.0 + 0.5) * Cylinder(tap_dia / 2.0, tap_depth + 1.0)
    return body
