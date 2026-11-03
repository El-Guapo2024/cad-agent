"""The fab's laser: a JPT Lark UV source, an SG7110 galvo and Jenoptik's telecentric lens on a bridge that focuses.

The laser stack, bottom up (as the earlier bridge): the board's top (B_TOP, the fixture's); the lens's 315.8 flange
to focus (Jenoptik JENar 170-355-140, its input end screwed up into the galvo); the SG7110 93.6; the spacer that puts
the galvo's input on the source's beam axis; the laser plate, the source hanging from it in line with the galvo;
two 4040 beams on it. The beams end in two plates on MGN15 carriages riding rails on two 4040 posts, outside
LumenPnP's frame (its gantry runs x -65 to 642 under the bridge), so the whole stack moves 20 mm in z: focus for 0.2
to 3 mm boards and the flip's mid-plane hold. Each post has a Tr8x2 screw on a NEMA 17 under its nut (Klipper's two
z steppers, levelled together).

The frame: x, y from the optical axis, z the machine's. The posts stand on the cabinet's top rails (z -100).
"""
from build123d import Pos, Rot
from cad_agent.state import build_part, bought_solid

SLUG = "laser_bridge"

B_TOP = 37.0                             # the board's top (fab_stage)
GALVO_H = 93.6                           # SG7110 (UV mirrors)
LENS_WD, LENS_FF = 235.8, 315.8          # Jenoptik JENar 170-355-140: back working distance, flange to focus
LENS_OUT = 129.1                         # its STEP's output face, z in the file (input end at 22.51, 106.6 long)
LENS_SHIFT = 118.5 / 2.0 - 45.0          # the lens under the galvo's output end, not its middle
SOURCE = (307.5, 121.2)                  # JPT Lark-355-5A: length, height (beam axis at mid-height)
SPACER_T = SOURCE[1] / 2.0 - GALVO_H / 2.0
GALVO_TOP = B_TOP + LENS_FF + GALVO_H    # 446.4
PLATE_BOT = GALVO_TOP + SPACER_T         # 460.2
PLATE_T = 10.0
PT = PLATE_BOT + PLATE_T                 # 470.2: the beams' underside
PLATE_X = (-45.0, 383.0)                 # the galvo's left end to the source's right end
POST_X = (-360.0, 450.0)                 # the posts' centres: machine x -100 and 710, clear of the gantry and the source
CAB_TOP, POST_TOP = -100.02, 560.0
Z_TRAVEL = 10.0
RAIL_Y, SCREW_Y = 12.0, -65.0            # the rail on the post's inner face; the screw beside the end plate
BEAM_Z = PT + 20.0                       # 490.2

CLEARANCE = {}


def _contact():
    c = {"bridge_beam_1|bridge_beam_2", "laser_plate|bridge_beam_1", "laser_plate|bridge_beam_2",
         "galvo_spacer|laser_plate", "galvo|galvo_spacer", "uv_source|laser_plate", "ftheta_lens|galvo"}
    for i in (1, 2):
        c |= {f"z_rail_{i}|bridge_post_{i}", f"z_block_{i}|z_rail_{i}", f"end_plate_{i}|z_block_{i}",
              f"bridge_beam_1|end_plate_{i}", f"bridge_beam_2|end_plate_{i}", f"z_ear_{i}|end_plate_{i}",
              f"t8_nut_{i}|z_ear_{i}", f"t8_nut_{i}|z_screw_{i}", f"z_coupling_{i}|z_screw_{i}",
              f"z_coupling_{i}|z_motor_{i}", f"z_motor_{i}|motor_mount_{i}", f"motor_mount_{i}|bridge_post_{i}"}
    return c


ALLOW_CONTACT = _contact()


def parts():
    p = lambda n, **o: build_part(SLUG, n, o or None)[0]
    b = lambda n, **o: bought_solid(SLUG, n, **o)
    out = {}
    # the laser stack
    gx = LENS_SHIFT
    out["laser_plate"] = Pos(sum(PLATE_X) / 2.0, 0, PLATE_BOT + PLATE_T / 2.0) * p("laser_plate")
    out["galvo_spacer"] = Pos(gx, 0, GALVO_TOP + SPACER_T / 2.0) * p("galvo_spacer")
    out["galvo"] = Pos(gx, 0, GALVO_TOP - GALVO_H / 2.0) * b("galvo", out_x=-gx)
    out["uv_source"] = Pos(PLATE_X[1] - SOURCE[0] / 2.0, 0, PLATE_BOT - SOURCE[1] / 2.0) * b("uv_source")
    flange = 49.01                     # the flange's face in the STEP (measured; 49.1 from the data sheet's numbers)
    out["ftheta_lens"] = Pos(0, 0, GALVO_TOP - GALVO_H + flange) * Rot(180, 0, 0) * b("ftheta_lens")
    # the bridge: posts, rails, carriages, end plates, beams
    ends = []
    for i, (x, s) in enumerate(zip(POST_X, (1, -1)), 1):          # s: toward the machine
        face = x + s * 20.0
        out[f"bridge_post_{i}"] = Pos(x, 0, (CAB_TOP + POST_TOP) / 2.0) * b("bridge_post")
        turn = Rot(0, 90 * s, 0)                                    # along z, its height toward the machine
        out[f"z_rail_{i}"] = Pos(face + s * 5.0, RAIL_Y, BEAM_Z) * turn * b("z_rail")
        out[f"z_block_{i}"] = Pos(face + s * 10.0, RAIL_Y, BEAM_Z) * turn * b("z_block")
        plate_in = face + s * 16.0                                  # the carriage's top face
        out[f"end_plate_{i}"] = Pos(plate_in + s * 5.0, 0, BEAM_Z) * p("end_plate")
        ends.append(plate_in + s * 10.0)
        sx = plate_in + s * 1.0                                     # the screw, its nut on the ear
        out[f"z_ear_{i}"] = Pos(plate_in + s * 9.0 - s * 8.0, SCREW_Y, BEAM_Z + 15.8) * p("z_ear")
        ear_top = BEAM_Z + 15.8 + 6.0
        out[f"t8_nut_{i}"] = Pos(sx, SCREW_Y, ear_top + 3.5) * b("t8_nut")
        c_top = 430.0
        out[f"z_coupling_{i}"] = Pos(sx, SCREW_Y, c_top - 14.5) * b("coupling")
        s0, s1 = c_top - 14.5, ear_top + 3.5 + Z_TRAVEL + 20.0
        out[f"z_screw_{i}"] = Pos(sx, SCREW_Y, (s0 + s1) / 2.0) * b("t8_screw", length=s1 - s0)
        mface = c_top - 29.0 - (23.88 - 14.5)
        out[f"motor_mount_{i}"] = Pos(sx, SCREW_Y, mface + 3.0) * Rot(0, 90, 0) * p(
            "motor_mount", size_y=90.0, size_z=50.0, bore_z=0.0)
        out[f"z_motor_{i}"] = Pos(sx, SCREW_Y, mface) * b("z_motor")
    x0, x1 = ends
    for k, y in ((1, -20.0), (2, 20.0)):
        out[f"bridge_beam_{k}"] = Pos((x0 + x1) / 2.0, y, BEAM_Z) * b("bridge_beam")
    return out


_FIXED = ("bridge_post", "z_rail", "z_coupling", "z_screw", "motor_mount", "z_motor")
AXES = {"z": {"moves": tuple(n for n in ("laser_plate", "galvo_spacer", "galvo", "uv_source", "ftheta_lens",
                                         "bridge_beam_1", "bridge_beam_2", "z_block_1", "z_block_2", "end_plate_1",
                                         "end_plate_2", "z_ear_1", "z_ear_2", "t8_nut_1", "t8_nut_2")),
              "direction": (0, 0, 1), "travel": (-Z_TRAVEL, Z_TRAVEL), "work": (-Z_TRAVEL, Z_TRAVEL)}}
POSES = {"focus_low": {"z": -Z_TRAVEL}, "focus_high": {"z": Z_TRAVEL}}
