"""Materials: density, stiffness, strength and service temperature, with where every number came from.

This is Python source and not a data file on purpose: `verify.engine_hash` hashes cad_agent/**/*.py and
the build cache keys on the engine hash, so a value changed here changes what a verdict means and
what a cached part is worth, the same as a change to a rule. `geom.DENSITY` is derived from it.

What a material holds, in the units of its key:

    density_g_cm3         FreeCAD's Density (kg/m^3), in g/cm^3
    youngs_modulus_mpa    YoungsModulus
    poisson_ratio         PoissonRatio
    yield_strength_mpa    YieldStrength
    max_service_temp_c    MaxServiceTemperature: FreeCAD's cards have none, so this slot is ours (step 6,
                          piece C1 fills it)

and `card`, the name of the FreeCAD material card it follows. Each property is `None` (nothing in a
source we can cite: a rule that needs it is UNCHECKED, by design) or a tuple `(value, source)`:

    source   either `FreeCAD 3160daf1e2b6 src/Mod/Material/Resources/Materials/<card>.FCMat: <Key> = <as the card writes it>`
             (build it with `fc()`), or `<https URL>: <document and the number it says>` (`ds()`).

A source says what a reader needs to look the number up, and tests/test_materials.py reads it back: a
card's own text must give the value after the unit conversion, and a datasheet's text must contain it.
`max_service_temp_c` takes `(value_c, source_url, basis)`, and the basis is one of MAX_TEMP_BASES: heat
deflection temperature at 0.45 MPa (ISO 75-2 method B), a UL 746B relative thermal index, or a glass
transition. It is a ceiling for a part held at temperature for its life, not a melting point.

Densities
---------
The densities are the ones `geom.DENSITY` has always had, and `mass` rows in every verified design
rest on them, so they do not move. Where FreeCAD's card says something else the value stays and the
source is a datasheet: steel (card 7900 kg/m^3, kept 7850), stainless (7800, kept 8000), ABS (1060,
kept 1040), nylon (PA6 card 1150, kept 1140) and acrylic (1160, kept 1180). Stiffness and strength
come from the card where there is one. To follow FreeCAD's densities instead is a deliberate change
that moves every mass row of those materials.

The FreeCAD cards (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6) are used under their own
licences, which differ by card; CARDS lists each with its author, as CC-BY asks.
"""
from __future__ import annotations

from typing import NamedTuple

FREECAD_COMMIT = "3160daf1e2b6"
FREECAD_DIR = "src/Mod/Material/Resources/Materials/"

PROPERTIES = ("density_g_cm3", "youngs_modulus_mpa", "poisson_ratio", "yield_strength_mpa", "max_service_temp_c")
FREECAD_NAMES = {"density_g_cm3": "Density", "youngs_modulus_mpa": "YoungsModulus",
                 "poisson_ratio": "PoissonRatio", "yield_strength_mpa": "YieldStrength",
                 "max_service_temp_c": "MaxServiceTemperature"}
MAX_TEMP_BASES = ("HDT ISO 75-2 B", "UL 746B RTI", "Tg")


class Prop(NamedTuple):
    value: float
    source: str
    basis: str = ""            # only max_service_temp_c has one


def fc(card: str, key: str, as_written: str) -> str:
    """A FreeCAD card as a source: its path under the Materials folder, the property and its text."""
    return f"FreeCAD {FREECAD_COMMIT} {FREECAD_DIR}{card}: {key} = {as_written}"


def ds(url: str, what: str) -> str:
    """A datasheet as a source: where it is, which document, and the number it gives."""
    return f"{url}: {what}"


# The cards below, with their author and licence as the card gives them.
CARDS = {
    "Standard/Metal/Aluminum/Aluminum-Generic.FCMat": ("Aluminum Generic", "Uwe Stöhr", "LGPL-2.1-or-later"),
    "Standard/Metal/Steel/Steel-Generic.FCMat": ("Steel-Generic", "Juergen Riegel", "CC-BY-3.0"),
    "Standard/Metal/Steel/Steel-X5CrNi18-10.FCMat": ("X5CrNi18-10", "M. Münch", "LGPL-2.0-or-later"),
    "Standard/Metal/Copper/Copper-Generic.FCMat": ("Copper Generic", "Uwe Stöhr", "LGPL-2.1-or-later"),
    "Standard/Thermoplast/PLA-Generic.FCMat": ("PLA", "Uwe Stöhr", "CC-BY-3.0"),
    "Standard/Thermoplast/ABS-Generic.FCMat": ("ABS", "Juergen Riegel", "CC-BY-3.0"),
    "Standard/Thermoplast/PA6-Generic.FCMat": ("Polyamide 6", "Uwe Stöhr", "CC-BY-3.0"),
    "Standard/Thermoplast/Acrylic-Glass-Generic.FCMat": ("Acrylic Glass", "Przemo Firszt", "CC-BY-3.0"),
}

_AL = "Standard/Metal/Aluminum/Aluminum-Generic.FCMat"
_STEEL = "Standard/Metal/Steel/Steel-Generic.FCMat"
_SS = "Standard/Metal/Steel/Steel-X5CrNi18-10.FCMat"
_CU = "Standard/Metal/Copper/Copper-Generic.FCMat"
_PLA = "Standard/Thermoplast/PLA-Generic.FCMat"
_ABS = "Standard/Thermoplast/ABS-Generic.FCMat"
_PA6 = "Standard/Thermoplast/PA6-Generic.FCMat"
_PMMA = "Standard/Thermoplast/Acrylic-Glass-Generic.FCMat"

_A36 = "https://www.azom.com/article.aspx?ArticleID=6117"
_304L = "https://www.ametek.com/-/media/ameteksuperiortube/files/downloads/alloy-data-sheets/alloy304l.pdf"
_C36000 = "https://alloys.copper.org/alloy/C36000"
_PETG = "https://storage.googleapis.com/prusa3d-content-prod-14e8-wordpress-prusament-prod/2023/10/9f8d2165-tds_prusament-petg_n_en.pdf"
_GP22 = "https://protolabs.com/media/wyxjrany/terluran-gp-22.pdf"
_ZYTEL = "https://protolabs.com/media/tcebrq5j/zytel-101l.pdf"
_WK_PMMA = "https://wkfluidhandling.com/wp-content/media/materials/pmma-acrylic.pdf"
_G10 = "https://www.polymershapes.com/wp-content/uploads/2020/04/Polymershapes_Accurate_DataSheet-Acculam-Epoxyglas-G10-FR4.pdf"
_KAPTON = "https://www.epectec.com/downloads/DuPont-Kapton-HN-Polyimide-Film.pdf"

# The order is the order geom.DENSITY lists them in (`cad tables density`), each followed by its aliases.
MATERIALS: dict[str, dict] = {
    "aluminium": {
        "card": "Aluminum Generic",
        "density_g_cm3": (2.70, fc(_AL, "Density", "2700 kg/m^3")),
        "youngs_modulus_mpa": (70000.0, fc(_AL, "YoungsModulus", "70000 MPa")),
        "poisson_ratio": (0.35, fc(_AL, "PoissonRatio", "0.35")),
        "yield_strength_mpa": None,             # the Generic card has none: it is every alloy and temper
        "max_service_temp_c": None,
    },
    "steel": {
        "card": "Steel-Generic",
        "density_g_cm3": (7.85, ds(_A36, "AZoM, ASTM A36 mild/low carbon steel: Density 7.85 g/cm3")),
        "youngs_modulus_mpa": (200000.0, fc(_STEEL, "YoungsModulus", "200000 MPa")),
        "poisson_ratio": (0.3, fc(_STEEL, "PoissonRatio", "0.3")),
        "yield_strength_mpa": None,
        "max_service_temp_c": None,
    },
    "stainless": {
        "card": "X5CrNi18-10",
        "density_g_cm3": (8.00, ds(_304L, "Superior Tube alloy 304L data sheet: Density 8.00 g/cm3")),
        "youngs_modulus_mpa": (200000.0, fc(_SS, "YoungsModulus", "200000 MPa")),
        "poisson_ratio": (0.3, fc(_SS, "PoissonRatio", "0.3")),
        "yield_strength_mpa": (210.0, fc(_SS, "YieldStrength", "210 MPa")),
        "max_service_temp_c": None,
    },
    "brass": {
        "card": None,                            # FreeCAD has no brass card with mechanical values
        "density_g_cm3": (8.50, ds(_C36000, "Copper Development Association, alloy C36000 free-cutting brass: "
                                            "Specific Gravity 8.5")),
        "youngs_modulus_mpa": (96527.0, ds(_C36000, "CDA alloy C36000: Modulus of Elasticity in Tension "
                                                    "14000 ksi, 96527 MPa")),
        "poisson_ratio": None,
        "yield_strength_mpa": None,              # it depends on the temper
        "max_service_temp_c": None,
    },
    "copper": {
        "card": "Copper Generic",
        "density_g_cm3": (8.96, fc(_CU, "Density", "8960 kg/m^3")),
        "youngs_modulus_mpa": (119000.0, fc(_CU, "YoungsModulus", "119 GPa")),
        "poisson_ratio": (0.343, fc(_CU, "PoissonRatio", "0.343")),
        "yield_strength_mpa": (33.3, fc(_CU, "YieldStrength", "33.3 MPa")),
        "max_service_temp_c": None,
    },
    "pla": {
        "card": "PLA",
        "density_g_cm3": (1.24, fc(_PLA, "Density", "1240 kg/m^3")),
        "youngs_modulus_mpa": (3640.0, fc(_PLA, "YoungsModulus", "3640 MPa")),
        "poisson_ratio": (0.36, fc(_PLA, "PoissonRatio", "0.36")),
        "yield_strength_mpa": (35.9, fc(_PLA, "YieldStrength", "35.9 MPa")),
        "max_service_temp_c": None,
    },
    "petg": {
        "card": None,                            # FreeCAD's PET card is PET, not the glycol-modified copolymer
        "density_g_cm3": (1.27, ds(_PETG, "Prusament PETG technical datasheet v1.1, 2022-02-16: "
                                          "Density 1.27 g/cm3 (ISO 1183)")),
        "youngs_modulus_mpa": (1500.0, ds(_PETG, "Prusament PETG technical datasheet v1.1: Tensile Modulus "
                                                 "1.5 GPa (ISO 527-1, printed specimens, horizontal)")),
        "poisson_ratio": None,
        "yield_strength_mpa": (47.0, ds(_PETG, "Prusament PETG technical datasheet v1.1: Tensile Yield "
                                               "Strength 47 MPa (ISO 527-1, printed specimens, horizontal)")),
        "max_service_temp_c": None,
    },
    "abs": {
        "card": "ABS",
        "density_g_cm3": (1.04, ds(_GP22, "BASF Terluran GP-22 datasheet: Density 1.04 g/cm3 (ISO 1183)")),
        "youngs_modulus_mpa": (2300.0, fc(_ABS, "YoungsModulus", "2300 MPa")),
        "poisson_ratio": (0.37, fc(_ABS, "PoissonRatio", "0.37")),
        "yield_strength_mpa": (44.1, fc(_ABS, "YieldStrength", "44.1 MPa")),
        "max_service_temp_c": None,
    },
    "nylon": {
        "card": "Polyamide 6",
        "density_g_cm3": (1.14, ds(_ZYTEL, "Zytel 101L NC010 datasheet: Density 1.14 g/cm3 (ISO 1183)")),
        "youngs_modulus_mpa": (2930.0, fc(_PA6, "YoungsModulus", "2930 MPa")),
        "poisson_ratio": (0.39, fc(_PA6, "PoissonRatio", "0.39")),
        "yield_strength_mpa": (70.5, fc(_PA6, "YieldStrength", "70.5 MPa")),
        "max_service_temp_c": None,
    },
    "acrylic": {
        "card": "Acrylic Glass",
        "density_g_cm3": (1.18, ds(_WK_PMMA, "W-K Fluid Handling PMMA acrylic data sheet: Density 1.18 g/cm3 "
                                             "(ASTM D792)")),
        "youngs_modulus_mpa": (2550.0, fc(_PMMA, "YoungsModulus", "2550 MPa")),
        "poisson_ratio": (0.38, fc(_PMMA, "PoissonRatio", "0.38")),
        "yield_strength_mpa": (73.7, fc(_PMMA, "YieldStrength", "73.7 MPa")),
        "max_service_temp_c": None,
    },
    "fr4": {
        "card": None,                            # FreeCAD has glass fibre cards, not the laminate
        "density_g_cm3": (1.85, ds(_G10, "Polymershapes Acculam Epoxyglas G10/FR4 data sheet: "
                                         "Specific Gravity 1.85")),
        "youngs_modulus_mpa": None,              # a laminate: its modulus differs along and across the weave
        "poisson_ratio": None,
        "yield_strength_mpa": None,
        "max_service_temp_c": None,
    },
    "polyimide": {
        "card": None,
        "density_g_cm3": (1.42, ds(_KAPTON, "DuPont Kapton HN data sheet K-15345-2 (12/16): Density "
                                            "1.42 g/cm3 (the sheet's g/cc, ASTM D-1505)")),
        "youngs_modulus_mpa": (2500.0, ds(_KAPTON, "DuPont Kapton HN data sheet K-15345-2: Tensile Modulus "
                                                   "at 23 C 2.5 GPa (ASTM D-882)")),
        "poisson_ratio": (0.34, ds(_KAPTON, "DuPont Kapton HN data sheet K-15345-2: Poisson's Ratio 0.34")),
        "yield_strength_mpa": None,              # a film with no yield point
        "max_service_temp_c": None,
    },
}

ALIASES = {"aluminum": "aluminium"}


def key(name) -> str | None:
    """The name a material is stored under, or None when we do not know it ('Aluminum ' is 'aluminium')."""
    k = str(name).strip().lower()
    k = ALIASES.get(k, k)
    return k if k in MATERIALS else None


def names() -> tuple[str, ...]:
    return tuple(MATERIALS)


def get(name) -> dict | None:
    k = key(name)
    return MATERIALS[k] if k else None


def prop(name, which: str) -> Prop | None:
    """One property of a material with its source, or None: an unknown material, or a number no source gives.

    A rule that needs it and gets None is UNCHECKED, not a guess.
    """
    if which not in PROPERTIES:
        raise KeyError(f"unknown property {which!r}; known: {', '.join(PROPERTIES)}")
    material = get(name)
    value = material.get(which) if material else None
    return Prop(*value) if value else None


def density_table() -> dict[str, float]:
    """name -> g/cm^3 for every material and alias: what geom.DENSITY is."""
    out = {}
    for name, material in MATERIALS.items():
        out[name] = material["density_g_cm3"][0]
        out.update({alias: out[name] for alias, target in ALIASES.items() if target == name})
    return out


def table() -> dict:
    """Every material for `cad tables materials`: the numbers, and the source of each one."""
    out = {}
    for name, material in MATERIALS.items():
        row = {"card": material["card"],
               "aliases": [a for a, target in ALIASES.items() if target == name]}
        row.update({p: (material[p][0] if material[p] else None) for p in PROPERTIES})
        row["sources"] = {p: material[p][1] for p in PROPERTIES if material[p]}
        if material["max_service_temp_c"]:
            row["max_service_temp_basis"] = material["max_service_temp_c"][2]
        out[name] = row
    return out
