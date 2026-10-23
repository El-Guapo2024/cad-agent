"""ISO 286 limits and fits: the deviations of a hole or shaft tolerance class, for sizes up to 500 mm.

The numbers are ISO 286-1:2010, Table 1 (standard tolerance grades IT5 to IT11) and Tables 2 and 3
(fundamental deviations of shafts and holes), in micrometres, for the size ranges those tables use: over
the lower size, up to and including the upper. A class is a letter and a grade (H7, g6), and its two
deviations follow from those tables by ISO 286-1's rules, which is how ISO 286-2's class tables are made:

    a shaft a to h has its upper deviation es from Table 2 and ei = es - IT; js is +-IT/2; k to s have ei
    a hole D to H is the shaft's mirror, EI = -es; JS is +-IT/2; K, N, P, R and S (to IT8, IT8, IT7, IT7
    and IT7) have ES = -ei of the shaft letter plus delta = IT(n) - IT(n-1), except up to 3 mm, where delta is 0

tests/test_holes_fit.py checks the classes against published reproductions of the ISO 286-2 tables, over
3 to 400 mm: H7, H11, F7, G7, JS7, K7, N7, P7, g6, f7, h11, js6, k6 and p6 from cadforum.cz/en/tolerance.asp
and simplybearings.co.uk's ISO 286 page, d9 and e8 (and 400 to 500 mm) from Miki Pulley's JIS B 0401
excerpt, which has ISO 286's numbers; and the usual examples: 10 H7 is 0/+15, 10 g6 -5/-14, 25 H7/g6 a
clearance of 0.007 to 0.041 mm. It also checks every class FreeCAD's TechDraw Hole/Shaft Fit tool offers
(TechDrawTools/TaskHoleShaftFit.py, class ISO286, at 3160daf1e2b6: c11 f7 h6 h7 h9 k6 n6 r6 s6, D10 E9 F8
G7 H7 H8 H11 K7 N7 R7 S7) against a copy of that tool's tables at 27 sizes. They agree but for n6 over 160
mm, where FreeCAD's n row is one entry short: from 160 mm it gives the next range's value (170 n6 +35/+60,
which is +27/+52) and over 400 mm it raises IndexError.
"""
from __future__ import annotations

import re

# The size ranges of Table 1: over the one before, up to and including this one.
SIZES = (3, 6, 10, 18, 30, 50, 80, 120, 180, 250, 315, 400, 500)
IT = {      # standard tolerance, micrometres, per range of SIZES
    5: (4, 5, 6, 8, 9, 11, 13, 15, 18, 20, 23, 25, 27),
    6: (6, 8, 9, 11, 13, 16, 19, 22, 25, 29, 32, 36, 40),
    7: (10, 12, 15, 18, 21, 25, 30, 35, 40, 46, 52, 57, 63),
    8: (14, 18, 22, 27, 33, 39, 46, 54, 63, 72, 81, 89, 97),
    9: (25, 30, 36, 43, 52, 62, 74, 87, 100, 115, 130, 140, 155),
    10: (40, 48, 58, 70, 84, 100, 120, 140, 160, 185, 210, 230, 250),
    11: (60, 75, 90, 110, 130, 160, 190, 220, 250, 290, 320, 360, 400),
}
# Shafts' fundamental deviations, micrometres, per range of SIZES: es for c to h, ei for k to p.
UPPER = {
    "d": (-20, -30, -40, -50, -65, -80, -100, -120, -145, -170, -190, -210, -230),
    "e": (-14, -20, -25, -32, -40, -50, -60, -72, -85, -100, -110, -125, -135),
    "f": (-6, -10, -13, -16, -20, -25, -30, -36, -43, -50, -56, -62, -68),
    "g": (-2, -4, -5, -6, -7, -9, -10, -12, -14, -15, -17, -18, -20),
    "h": (0,) * 13,
}
LOWER = {
    "k": (0, 1, 1, 1, 2, 2, 2, 3, 3, 4, 4, 4, 5),      # for IT4 to IT7, the grades k is offered in here
    "m": (2, 4, 6, 7, 8, 9, 11, 13, 15, 17, 20, 21, 23),
    "n": (4, 8, 10, 12, 15, 17, 20, 23, 27, 31, 34, 37, 40),
    "p": (6, 12, 15, 18, 22, 26, 32, 37, 43, 50, 56, 62, 68),
}
# c, r and s change inside some ranges, so they have finer ones (Table 2's subdivided rows).
C_UPPER = ((3, -60), (6, -70), (10, -80), (18, -95), (30, -110), (40, -120), (50, -130), (65, -140),
           (80, -150), (100, -170), (120, -180), (140, -200), (160, -210), (180, -230), (200, -240),
           (225, -260), (250, -280), (280, -300), (315, -330), (355, -360), (400, -400), (450, -440),
           (500, -480))
R_LOWER = ((3, 10), (6, 15), (10, 19), (18, 23), (30, 28), (50, 34), (65, 41), (80, 43), (100, 51),
           (120, 54), (140, 63), (160, 65), (180, 68), (200, 77), (225, 80), (250, 84), (280, 94),
           (315, 98), (355, 108), (400, 114), (450, 126), (500, 132))
S_LOWER = ((3, 14), (6, 19), (10, 23), (18, 28), (30, 35), (50, 43), (65, 53), (80, 59), (100, 71),
           (120, 79), (140, 92), (160, 100), (180, 108), (200, 122), (225, 130), (250, 140), (280, 158),
           (315, 170), (355, 190), (400, 208), (450, 232), (500, 252))

SHAFT_GRADES = {"c": range(6, 12), "d": range(6, 12), "e": range(6, 12), "f": range(6, 12),
                "g": range(6, 12), "h": range(6, 12), "js": range(6, 12), "k": range(5, 8),
                "m": range(5, 8), "n": range(5, 8), "p": range(5, 8), "r": range(5, 8), "s": range(5, 8)}
HOLE_GRADES = {"D": range(6, 12), "E": range(6, 12), "F": range(6, 12), "G": range(6, 12), "H": range(6, 12),
               "JS": range(6, 12), "K": range(6, 9), "N": range(6, 9), "P": range(6, 8), "R": range(6, 8),
               "S": range(6, 8)}
FINER = {"r": R_LOWER, "s": S_LOWER}
CLASS = re.compile(r"([A-Za-z]{1,2})(\d{1,2})")


class FitError(ValueError):
    """A class it does not have, or a size outside 0 to 500 mm."""


def _range(size: float) -> int:
    if not 0 < size <= SIZES[-1]:
        raise FitError(f"ISO 286 is tabled here for sizes over 0 up to {SIZES[-1]} mm, not {size:g}")
    return next(i for i, top in enumerate(SIZES) if size <= top)


def _finer(rows, size: float) -> int:
    return next(v for top, v in rows if size <= top)


def _half(it: int) -> float:
    """js and JS: +-IT/2 exactly, as the published 286-2 tables give them (JS7 18-30 is +-10.5; some older
    tables round an odd IT7 to IT11 down to even first, +-10)."""
    return it / 2.0


def shaft(cls: str, size: float) -> tuple[float, float]:
    """(ei, es) of a shaft class such as "g6" at a nominal size, in micrometres."""
    letter, grade = _split(cls, SHAFT_GRADES, "shaft")
    i = _range(size)
    it = IT[grade][i]
    if letter == "js":
        return -_half(it), _half(it)
    if letter in UPPER or letter == "c":
        es = _finer(C_UPPER, size) if letter == "c" else UPPER[letter][i]
        return es - it, es
    return _ei(letter, size, i), _ei(letter, size, i) + it


def _ei(letter: str, size: float, i: int) -> int:
    """The lower deviation of a shaft letter k to s, micrometres."""
    return _finer(FINER[letter], size) if letter in FINER else LOWER[letter][i]


def hole(cls: str, size: float) -> tuple[float, float]:
    """(EI, ES) of a hole class such as "H7" at a nominal size, in micrometres."""
    letter, grade = _split(cls, HOLE_GRADES, "hole")
    i = _range(size)
    it = IT[grade][i]
    if letter == "JS":
        return -_half(it), _half(it)
    if letter in ("D", "E", "F", "G", "H"):
        ei = -UPPER[letter.lower()][i]
        return ei, ei + it
    delta = 0 if size <= 3 else it - IT[grade - 1][i]
    es = -_ei(letter.lower(), size, i) + delta
    return es - it, es


def clearance(fit: str, size: float) -> tuple[float, float]:
    """(least, most) bore minus shaft, in mm, of a fit such as "H7/g6" at a nominal size; below 0 is interference."""
    if not isinstance(fit, str) or fit.count("/") != 1:
        raise FitError(f"a fit is a hole class over a shaft class, such as \"H7/g6\", not {fit!r}")
    h, s = fit.split("/")
    (lo_h, hi_h), (lo_s, hi_s) = hole(h.strip(), size), shaft(s.strip(), size)
    return (lo_h - hi_s) / 1000.0, (hi_h - lo_s) / 1000.0


def _split(cls: str, grades: dict, what: str) -> tuple[str, int]:
    m = CLASS.fullmatch(cls)
    if not m or m.group(1) not in grades or int(m.group(2)) not in grades[m.group(1)]:
        known = ", ".join(f"{k}{g[0]}-{g[-1]}" for k, g in grades.items())
        raise FitError(f"no ISO 286 {what} class {cls!r} here (known: {known})")
    return m.group(1), int(m.group(2))
