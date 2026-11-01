"""LumenPnP v4.2.0 by Opulo, the base pcbfab builds on: its own FreeCAD assembly, exported group by group.

Source: https://github.com/opulo-inc/lumenpnp at 64cf68d (2026-10-14), src/assembly.FCStd, opened in FreeCAD
2026.09.30 and each top-level group of the assembly exported to STEP in the assembly's coordinates (bought/*.json name
the group). Hardware licence CERN-OHL-W v2: changes to these files are shared back under the same licence; the
names Opulo and LumenPnP are their trademarks.

Frame (theirs): x along the front feeder rail (0 to 600), y from the front rail (y ~ 0) to the rear rail (y ~ 440),
z up; the feeder rails' tops are at z 20 and the frame's feet at z -101 (the table).

control_box (their electronics) is left out: pcbfab replaces it with its own (Jetson, Klipper). Its STEP stays in
bought/ for reference.
"""
from cad_agent.state import bought_solid

SLUG = "lumenpnp"

GROUPS = ("y_gantry_left", "y_gantry_right", "x_gantry", "front_feeder_rail", "rear_feeder_rail",
          "y_limit_striker", "x_drag_chain_asm", "y_drag_chain_asm", "primary_staging_plate",
          "optional_strip_feeders", "components_installed_by_user")

CLEARANCE = {}
# Their own parts touching or nested in one another as modelled (screws and nuts sitting in holes, cable chain links
# on their brackets): 7 to 330 mm^3 each in `cad check`. Their design, not a fit to judge here.
ALLOW_CONTACT = {
    "components_installed_by_user|front_feeder_rail", "components_installed_by_user|rear_feeder_rail",
    "components_installed_by_user|x_drag_chain_asm", "components_installed_by_user|x_gantry",
    "components_installed_by_user|y_drag_chain_asm", "components_installed_by_user|y_gantry_left",
    "components_installed_by_user|y_gantry_right", "x_drag_chain_asm|x_gantry", "x_drag_chain_asm|y_drag_chain_asm",
}


def parts():
    return {g: bought_solid(SLUG, g) for g in GROUPS}
