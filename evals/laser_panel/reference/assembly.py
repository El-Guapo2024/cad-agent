"""Front panel assembly: the panel on the frame, the button and the OLED in their cutouts.

Coordinates: +z toward the user, x to the right, y up. The origin is the middle of the
frame's front face, so the frame fills z = -8 to 0 and the panel z = 0 to 3.

The three given bodies are STEP files whose origin is their bounding-box centre, so each one
is placed by `Pos(centre)` with the centre the brief states. The button's seat plane (where
its barrel meets the panel's front face) lands on z = 3, and the OLED's PCB lands 0.8 mm
behind the panel, its glass poking 0.57 mm into the window.

The panel is the only body that is designed. It rests on the frame, and neither component
touches it: the button's flange and nut, and the tape under the OLED, are not modelled, so
what separates each component from the panel is the cutout.
"""
from build123d import Pos
from cad_agent.state import build_part, bought_solid

SLUG = "laser_panel"
PANEL_T = 3.0

CLEARANCE = {
    "push_button|panel": 0.1,   # barrel to the edge of its hole
    "oled|panel": 0.1,          # glass to the edge of its window
}

ALLOW_CONTACT = {"frame|panel"}  # the panel sits on the frame, held by four M3 screws


def parts():
    panel, _ = build_part(SLUG, "panel")
    return {
        "frame": Pos(0, 0, -4.0) * bought_solid(SLUG, "frame"),
        "panel": Pos(0, 0, PANEL_T / 2.0) * panel,
        "push_button": Pos(-22.5, 0, -6.7) * bought_solid(SLUG, "push_button"),
        "oled": Pos(17.5, 0, -4.365) * bought_solid(SLUG, "oled"),
    }
