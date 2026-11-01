"""Laser bed: the pinned aluminium plate the board lies on while the galvo etches and drills it.

The hot plate's own design (same size, same two registration-pin holes on the same pitch), so a board drilled and
etched here drops onto the hot plate's pins in the same place. Not heated.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from hot_plate import PARAMS as _HOT, build as _build

MATERIAL = "aluminium"
PROCESS = "cnc"
MIN_FEATURE_MM = 3.0
EXPECT_FEATURES = 6

PARAMS = dict(_HOT)


def build(**params):
    return _build(**params)
