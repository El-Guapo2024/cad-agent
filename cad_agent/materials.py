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
                          piece C1; see "Service temperatures" below)

and `card`, the name of the FreeCAD material card it follows. Each property is `None` (nothing in a
source we can cite: a rule that needs it is UNCHECKED, by design) or a tuple `(value, source)`:

    source   either `FreeCAD 3160daf1e2b6 src/Mod/Material/Resources/Materials/<card>.FCMat: <Key> = <as the card writes it>`
             (build it with `fc()`), or `<https URL>: <document and the number it says>` (`ds()`).

A source says what a reader needs to look the number up, and tests/test_materials.py reads it back: a
card's own text must give the value after the unit conversion, and a datasheet's text must contain it.
`max_service_temp_c` takes `(value_c, source_url, basis)`, and the basis is one of MAX_TEMP_BASES: heat
deflection temperature at 0.45 MPa (ISO 75-2 method B), a UL 746B relative thermal index, a glass
transition, or the service limit a maker or handbook states. It is a ceiling for a part held at
temperature for its life, not a melting point.

Service temperatures
--------------------
One number per material, in degrees C, that the `[[heat]]` rule holds a body to. Which kind of number it
is differs by material, because no one kind exists for all of them, and the basis says which:

  HDT ISO 75-2 B        the thermoplastics (PLA, PETG, ABS, nylon): the temperature at which a bar bends
                        0.25 mm under 0.45 MPa. It is where a part starts to give under a light load, not
                        a life rating (a UL RTI is lower), so a design that must last asks `[[heat]]` for a
                        `margin_c`. A sheet that gives HDT at 0.45 MPa and nothing else is read that way.
  Tg                    a film or thermoset with no HDT on its sheet (polyimide): the low end of the
                        glass transition the sheet gives.
  stated service limit  what the maker or a handbook says the material may sit at: acrylic and FR4 (the
                        sheet states it), and the metals, which have no HDT, RTI or Tg. For the metals it
                        is MakeItFrom.com's "Maximum Temperature: Mechanical" for the alloy the table's
                        density and card stand for (6061-T6 170 C, brass C36000 120 C, copper C11000
                        200 C, A36 400 C, 304 710 C), the same kind of number for all five. A range on a
                        sheet is read at its low end.

So steel, stainless and polyimide clear a 250 C zone and aluminium, brass and copper do not: a loaded part
at a heater's temperature is what the rule exists to catch (the heater's own plate is the `source` and
is exempt). A value nobody can cite is `None`.

Densities
---------
The densities are the ones `geom.DENSITY` has always had, and `mass` rows in every verified design
rest on them, so they do not move. Where FreeCAD's card says something else the value stays and the
source is a datasheet: steel (card 7900 kg/m^3, kept 7850), stainless (7800, kept 8000), ABS (1060,
kept 1040), nylon (PA6 card 1150, kept 1140) and acrylic (1160, kept 1180). Stiffness and strength
come from the card where there is one. To follow FreeCAD's densities instead is a deliberate change
that moves every mass row of those materials.

Nylon is a PA6 everywhere but in one number: its stiffness and strength are the PA6 card's, its service
temperature is a PA6 sheet's (Zytel 7335F, an unreinforced PA6: 180 C, ISO 75-2/B, dry), and its density
is still the one cited to Zytel 101L, a PA66, because 1.14 is what every mass has used (the PA6 sheet says
1.13, the card 1.15). The service temperature once cited that same PA66 sheet (190 C), which is a hotter
polymer than the card describes.

Credit
------
The FreeCAD cards (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6) are used under their own
licences, which differ by card: five are CC-BY-3.0 (Juergen Riegel, Uwe Stöhr and Przemo Firszt), two are
LGPL-2.1-or-later (Uwe Stöhr) and one is LGPL-2.0-or-later (M. Münch). CARDS lists each with its author and
licence, LICENCE_URLS has the URL of each licence, and `credit()` writes what CC BY 3.0 section 4 asks for when a
value of the card is shown: the author's name, the title of the work, the licence's URL, where the card is, and
that the value is the card's own. It is printed wherever a value of a CC-BY card is shown: in the rows of
`cad tables materials` (and as `credits` in `cad tables`, `cad tables density` and `cad tables materials`) and
in the E of a `[[deflection]]` row. The licence texts are in THIRD_PARTY_LICENSES and the card list is in NOTICE.
"""
from __future__ import annotations

import re
from typing import NamedTuple

FREECAD_COMMIT = "3160daf1e2b6"
FREECAD_COMMIT_FULL = "3160daf1e2b62b0472854da4848255c6b3ad554c"
FREECAD_DIR = "src/Mod/Material/Resources/Materials/"

PROPERTIES = ("density_g_cm3", "youngs_modulus_mpa", "poisson_ratio", "yield_strength_mpa", "max_service_temp_c")
FREECAD_NAMES = {"density_g_cm3": "Density", "youngs_modulus_mpa": "YoungsModulus",
                 "poisson_ratio": "PoissonRatio", "yield_strength_mpa": "YieldStrength",
                 "max_service_temp_c": "MaxServiceTemperature"}
MAX_TEMP_BASES = ("HDT ISO 75-2 B", "UL 746B RTI", "Tg", "stated service limit")


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


class Card(NamedTuple):
    name: str           # the card's Name
    author: str         # its Author
    licence: str        # its License, as an SPDX identifier


# The cards below, with their name, author and licence as the card gives them (General: Name, Author, License).
CARDS = {path: Card(*fields) for path, fields in {
    "Standard/Metal/Aluminum/Aluminum-Generic.FCMat": ("Aluminum Generic", "Uwe Stöhr", "LGPL-2.1-or-later"),
    "Standard/Metal/Steel/Steel-Generic.FCMat": ("Steel-Generic", "Juergen Riegel", "CC-BY-3.0"),
    "Standard/Metal/Steel/Steel-X5CrNi18-10.FCMat": ("X5CrNi18-10", "M. Münch", "LGPL-2.0-or-later"),
    "Standard/Metal/Copper/Copper-Generic.FCMat": ("Copper Generic", "Uwe Stöhr", "LGPL-2.1-or-later"),
    "Standard/Thermoplast/PLA-Generic.FCMat": ("PLA", "Uwe Stöhr", "CC-BY-3.0"),
    "Standard/Thermoplast/ABS-Generic.FCMat": ("ABS", "Juergen Riegel", "CC-BY-3.0"),
    "Standard/Thermoplast/PA6-Generic.FCMat": ("Polyamide 6", "Uwe Stöhr", "CC-BY-3.0"),
    "Standard/Thermoplast/Acrylic-Glass-Generic.FCMat": ("Acrylic Glass", "Przemo Firszt", "CC-BY-3.0"),
}.items()}

# Where each licence's terms are. CC BY 3.0 section 4(a) wants a copy of the licence, or its URI, with every copy of the
# work; the texts of the CC and BSD licences are in THIRD_PARTY_LICENSES, and the LGPL's is in ui/LICENSE.
LICENCE_URLS = {
    "CC-BY-3.0": "https://creativecommons.org/licenses/by/3.0/",
    "LGPL-2.1-or-later": "https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html",
    "LGPL-2.0-or-later": "https://www.gnu.org/licenses/old-licenses/lgpl-2.0.html",
}
_CARD_IN_SOURCE = re.compile(rf"^FreeCAD {FREECAD_COMMIT} {re.escape(FREECAD_DIR)}(?P<card>\S+\.FCMat): ")


def card_url(card: str) -> str:
    """Where a card is, at the pinned commit (the work's URI, for the credit)."""
    return f"https://github.com/FreeCAD/FreeCAD/blob/{FREECAD_COMMIT_FULL}/{FREECAD_DIR}{card}"


def card_of(source: str) -> str | None:
    """The card a source cites (`fc()` builds those), or None for a datasheet."""
    m = _CARD_IN_SOURCE.match(source or "")
    return m["card"] if m else None


def needs_credit(card: str) -> bool:
    """Whether the card's licence asks for attribution wherever its values are shown: CC BY does, the LGPL does not."""
    return CARDS[card].licence.startswith("CC-BY")


def credit(card: str, short: bool = False) -> str:
    """The attribution CC BY 3.0 section 4(b) asks for, for a card: the author, the title of the work, the licence's
    URL and, in full, where the card is and that the value is the card's own. `short` is for a line of a report."""
    c = CARDS[card]
    if short:
        return f'"{c.name}" by {c.author}, {c.licence} {LICENCE_URLS[c.licence]}'
    return (f'"{c.name}", a FreeCAD material card by {c.author}, licensed {c.licence} ({LICENCE_URLS[c.licence]}): '
            f"{card_url(card)}; the values taken from it are the card's own, in g/cm3 and MPa")


def credit_suffix(source: str) -> str:
    """What follows a source where it is shown beside a value: a CC-BY card's short credit in brackets, else nothing. The
    source itself is never touched (tests/test_materials.py reads it back)."""
    card = card_of(source)
    return f" [{credit(card, short=True)}]" if card and needs_credit(card) else ""


def credits(properties=None) -> list[str]:
    """The credit of every CC-BY card behind the given properties of any material (all of them by default), once each."""
    wanted = PROPERTIES if properties is None else tuple(properties)
    cards = []
    for material in MATERIALS.values():
        for p in wanted:
            card = card_of(material[p][1]) if material.get(p) else None
            if card and needs_credit(card) and card not in cards:
                cards.append(card)
    return [credit(c) for c in cards]

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
# The service temperatures (see the docstring): the sheets for the plastics, MakeItFrom.com for the metals.
_PRUSA_PLA = "https://www.matterhackers.com/r/xFvGl8"          # the Prusament PLA datasheet, as MatterHackers hosts it
_ZYTEL_PA6 = "https://www.protolabs.com/media/tqzke2yx/zytel-7335f-nc010.pdf"     # a PA6, as Protolabs hosts its sheet
_GUND_FR4 = "https://thegundcompany.com/wp-content/uploads/2024/03/NEMA-FR4-Glass-Epoxy-Laminate-by-The-Gund-Co.pdf"
_MIF = "https://www.makeitfrom.com/material-properties/"
_MIF_6061 = _MIF + "6061-T6-Aluminum"
_MIF_A36 = _MIF + "ASTM-A36-SS400-S275-Structural-Carbon-Steel"
_MIF_304 = _MIF + "AISI-304-S30400-Stainless-Steel"
_MIF_C36000 = _MIF + "UNS-C36000-CW603N-Free-Cutting-Brass"
_MIF_C11000 = _MIF + "UNS-C11000-CW004A-Electrolytic-Tough-Pitch-Copper"

# The order is the order geom.DENSITY lists them in (`cad tables density`), each followed by its aliases.
MATERIALS: dict[str, dict] = {
    "aluminium": {
        "card": "Aluminum Generic",
        "density_g_cm3": (2.70, fc(_AL, "Density", "2700 kg/m^3")),
        "youngs_modulus_mpa": (70000.0, fc(_AL, "YoungsModulus", "70000 MPa")),
        "poisson_ratio": (0.35, fc(_AL, "PoissonRatio", "0.35")),
        "yield_strength_mpa": None,             # the Generic card has none: it is every alloy and temper
        "max_service_temp_c": (170.0, ds(_MIF_6061, "MakeItFrom.com, 6061-T6 aluminum, Thermal Properties: "
                                                   "Maximum Temperature: Mechanical 170 °C (330 °F)"),
                               "stated service limit"),
    },
    "steel": {
        "card": "Steel-Generic",
        "density_g_cm3": (7.85, ds(_A36, "AZoM, ASTM A36 mild/low carbon steel: Density 7.85 g/cm3")),
        "youngs_modulus_mpa": (200000.0, fc(_STEEL, "YoungsModulus", "200000 MPa")),
        "poisson_ratio": (0.3, fc(_STEEL, "PoissonRatio", "0.3")),
        "yield_strength_mpa": None,
        "max_service_temp_c": (400.0, ds(_MIF_A36, "MakeItFrom.com, ASTM A36 (SS400, S275) structural carbon steel, "
                                                  "Thermal Properties: Maximum Temperature: Mechanical 400 °C (750 °F)"),
                               "stated service limit"),
    },
    "stainless": {
        "card": "X5CrNi18-10",
        "density_g_cm3": (8.00, ds(_304L, "Superior Tube alloy 304L data sheet: Density 8.00 g/cm3")),
        "youngs_modulus_mpa": (200000.0, fc(_SS, "YoungsModulus", "200000 MPa")),
        "poisson_ratio": (0.3, fc(_SS, "PoissonRatio", "0.3")),
        "yield_strength_mpa": (210.0, fc(_SS, "YieldStrength", "210 MPa")),
        "max_service_temp_c": (710.0, ds(_MIF_304, "MakeItFrom.com, AISI 304 (S30400) stainless steel, Thermal "
                                                  "Properties: Maximum Temperature: Mechanical 710 °C (1300 °F); "
                                                  "its Maximum Temperature: Corrosion is 420 °C (790 °F)"),
                               "stated service limit"),
    },
    "brass": {
        "card": None,                            # FreeCAD has no brass card with mechanical values
        "density_g_cm3": (8.50, ds(_C36000, "Copper Development Association, alloy C36000 free-cutting brass: "
                                            "Specific Gravity 8.5")),
        "youngs_modulus_mpa": (96527.0, ds(_C36000, "CDA alloy C36000: Modulus of Elasticity in Tension "
                                                    "14000 ksi, 96527 MPa")),
        "poisson_ratio": None,
        "yield_strength_mpa": None,              # it depends on the temper
        "max_service_temp_c": (120.0, ds(_MIF_C36000, "MakeItFrom.com, UNS C36000 (CW603N) free-cutting brass, "
                                                     "Thermal Properties: Maximum Temperature: Mechanical 120 °C "
                                                     "(250 °F)"),
                               "stated service limit"),
    },
    "copper": {
        "card": "Copper Generic",
        "density_g_cm3": (8.96, fc(_CU, "Density", "8960 kg/m^3")),
        "youngs_modulus_mpa": (119000.0, fc(_CU, "YoungsModulus", "119 GPa")),
        "poisson_ratio": (0.343, fc(_CU, "PoissonRatio", "0.343")),
        "yield_strength_mpa": (33.3, fc(_CU, "YieldStrength", "33.3 MPa")),
        "max_service_temp_c": (200.0, ds(_MIF_C11000, "MakeItFrom.com, UNS C11000 (CW004A) electrolytic tough pitch "
                                                     "copper, Thermal Properties: Maximum Temperature: Mechanical "
                                                     "200 °C (390 °F)"),
                               "stated service limit"),
    },
    "pla": {
        "card": "PLA",
        "density_g_cm3": (1.24, fc(_PLA, "Density", "1240 kg/m^3")),
        "youngs_modulus_mpa": (3640.0, fc(_PLA, "YoungsModulus", "3640 MPa")),
        "poisson_ratio": (0.36, fc(_PLA, "PoissonRatio", "0.36")),
        "yield_strength_mpa": (35.9, fc(_PLA, "YieldStrength", "35.9 MPa")),
        "max_service_temp_c": (55.0, ds(_PRUSA_PLA, "Prusament PLA technical datasheet v1.1 (27-07-2022), as hosted by "
                                                   "MatterHackers: Heat Deflection Temperature (0.45 MPa) 55 °C "
                                                   "(ISO 75)"),
                               "HDT ISO 75-2 B"),
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
        "max_service_temp_c": (68.0, ds(_PETG, "Prusament PETG technical datasheet v1.1: Heat Deflection "
                                              "Temperature (0.45 MPa) 68 °C (ISO 75)"),
                               "HDT ISO 75-2 B"),
    },
    "abs": {
        "card": "ABS",
        "density_g_cm3": (1.04, ds(_GP22, "BASF Terluran GP-22 datasheet: Density 1.04 g/cm3 (ISO 1183)")),
        "youngs_modulus_mpa": (2300.0, fc(_ABS, "YoungsModulus", "2300 MPa")),
        "poisson_ratio": (0.37, fc(_ABS, "PoissonRatio", "0.37")),
        "yield_strength_mpa": (44.1, fc(_ABS, "YieldStrength", "44.1 MPa")),
        "max_service_temp_c": (99.0, ds(_GP22, "INEOS Styrolution Terluran GP-22 datasheet (UL Prospector "
                                              "TDS-37722-en): Deflection Temperature Under Load 0.45 MPa, Annealed "
                                              "99.0 °C (ISO 75-2/B)"),
                               "HDT ISO 75-2 B"),
    },
    "nylon": {
        "card": "Polyamide 6",
        "density_g_cm3": (1.14, ds(_ZYTEL, "Zytel 101L NC010 datasheet: Density 1.14 g/cm3 (ISO 1183)")),
        "youngs_modulus_mpa": (2930.0, fc(_PA6, "YoungsModulus", "2930 MPa")),
        "poisson_ratio": (0.39, fc(_PA6, "PoissonRatio", "0.39")),
        "yield_strength_mpa": (70.5, fc(_PA6, "YieldStrength", "70.5 MPa")),
        "max_service_temp_c": (180.0, ds(_ZYTEL_PA6, "Celanese Zytel 7335F NC010 datasheet (unreinforced, nucleated "
                                                     "polyamide 6; UL Prospector TDS-40236-en): Deflection "
                                                     "Temperature Under Load 0.45 MPa, Unannealed, Dry 180 °C "
                                                     "(ISO 75-2/B)"),
                               "HDT ISO 75-2 B"),
    },
    "acrylic": {
        "card": "Acrylic Glass",
        "density_g_cm3": (1.18, ds(_WK_PMMA, "W-K Fluid Handling PMMA acrylic data sheet: Density 1.18 g/cm3 "
                                             "(ASTM D792)")),
        "youngs_modulus_mpa": (2550.0, fc(_PMMA, "YoungsModulus", "2550 MPa")),
        "poisson_ratio": (0.38, fc(_PMMA, "PoissonRatio", "0.38")),
        "yield_strength_mpa": (73.7, fc(_PMMA, "YieldStrength", "73.7 MPa")),
        "max_service_temp_c": (65.0, ds(_WK_PMMA, "W-K Fluid Handling PMMA acrylic data sheet: Max Operating Temp "
                                                 "150-200 °F / 65-93 °C, read at its low end (the sheet covers "
                                                 "extruded, cast and moulded grades)"),
                               "stated service limit"),
    },
    "fr4": {
        "card": None,                            # FreeCAD has glass fibre cards, not the laminate
        "density_g_cm3": (1.85, ds(_G10, "Polymershapes Acculam Epoxyglas G10/FR4 data sheet: "
                                         "Specific Gravity 1.85")),
        "youngs_modulus_mpa": None,              # a laminate: its modulus differs along and across the weave
        "poisson_ratio": None,
        "yield_strength_mpa": None,
        "max_service_temp_c": (130.0, ds(_GUND_FR4, "The Gund Company NEMA FR4 glass epoxy laminate technical data "
                                                   "sheet (TGCR 06/2026): Temperature Index 130 °C (ASTM D2304); "
                                                   "properties held at elevated temperatures of up to 130 °C"),
                               "stated service limit"),
    },
    "polyimide": {
        "card": None,
        "density_g_cm3": (1.42, ds(_KAPTON, "DuPont Kapton HN data sheet K-15345-2 (12/16): Density "
                                            "1.42 g/cm3 (the sheet's g/cc, ASTM D-1505)")),
        "youngs_modulus_mpa": (2500.0, ds(_KAPTON, "DuPont Kapton HN data sheet K-15345-2: Tensile Modulus "
                                                   "at 23 C 2.5 GPa (ASTM D-882)")),
        "poisson_ratio": (0.34, ds(_KAPTON, "DuPont Kapton HN data sheet K-15345-2: Poisson's Ratio 0.34")),
        "yield_strength_mpa": None,              # a film with no yield point
        "max_service_temp_c": (360.0, ds(_KAPTON, "DuPont Kapton HN data sheet K-15345-2: a second order transition "
                                                 "between 360 °C (680 °F) and 410 °C (770 °F), assumed to be the "
                                                 "glass transition, read at its low end"),
                               "Tg"),
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
    """Every material for `cad tables materials`: the numbers, the source of each one and, for each FreeCAD card a
    number comes from, its credit (author, licence and its URL)."""
    out = {}
    for name, material in MATERIALS.items():
        row = {"card": material["card"],
               "aliases": [a for a, target in ALIASES.items() if target == name]}
        row.update({p: (material[p][0] if material[p] else None) for p in PROPERTIES})
        row["sources"] = {p: material[p][1] for p in PROPERTIES if material[p]}
        cards = []
        for p in PROPERTIES:
            card = card_of(material[p][1]) if material[p] else None
            if card and card not in cards:
                cards.append(card)
        row["credit"] = [credit(c) for c in cards]
        if material["max_service_temp_c"]:
            row["max_service_temp_basis"] = material["max_service_temp_c"][2]
        out[name] = row
    return out
