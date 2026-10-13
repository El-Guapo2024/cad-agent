"""Materials: every number has a source, and the densities that masses rest on did not move.

materials.py holds each value with where it came from: a FreeCAD material card (path, property and
the card's own text, at commit 3160daf1e2b6) or a datasheet (URL and the number it gives). These
tests read the sources back, so a value cannot drift from its card and a card cannot be named that
is not one of the eight listed with their licences. geom.DENSITY is derived from the table and has to
be what it always was, because the `mass` rows of every verified design rest on it.
"""
import json
import re
from pathlib import Path

import pytest
from build123d import Box

from cad_agent import cli, geom, materials, verify
from cad_agent.materials import CARDS, FREECAD_COMMIT, MATERIALS, MAX_TEMP_BASES, PROPERTIES, Prop

# geom.DENSITY as it was before materials.py: g/cm^3, in this order (`cad tables density` prints it).
LEGACY_DENSITY = {
    "aluminium": 2.70, "aluminum": 2.70, "steel": 7.85, "stainless": 8.00, "brass": 8.50, "copper": 8.96,
    "pla": 1.24, "petg": 1.27, "abs": 1.04, "nylon": 1.14, "acrylic": 1.18, "fr4": 1.85, "polyimide": 1.42,
}

TO_CANONICAL = {   # to g/cm^3 for a density, MPa for a stress
    "kg/m^3": 0.001, "g/cm^3": 1.0, "g/cm3": 1.0, "MPa": 1.0, "GPa": 1000.0,
    "ksi": 6.894757293168361, "psi": 0.006894757293168361,
}
QUANTITY = re.compile(r"(?<![\w.])(\d[\d,]*\.?\d*)\s*(kg/m\^3|g/cm\^3|g/cm3|MPa|GPa|ksi|psi)(?![\w/^])")
CARD_SOURCE = re.compile(rf"^FreeCAD {FREECAD_COMMIT} {re.escape(materials.FREECAD_DIR)}"
                         r"(?P<card>\S+\.FCMat): (?P<key>\w+) = (?P<raw>.+)$")
SHEET_SOURCE = re.compile(r"^(?P<url>https://\S+): (?P<what>.+)$")


def given(prop_name, material):
    return material[prop_name]


def converted(text):
    """Every quantity in a text, in the canonical unit of its own: the values it could be giving."""
    return [float(n.replace(",", "")) * TO_CANONICAL[u] for n, u in QUANTITY.findall(text)]


def sources():
    """Every (value, source) a material cites: max_service_temp_c is left out, it has a basis as well and
    tests/test_heat.py reads its numbers back."""
    for name, material in MATERIALS.items():
        for p in PROPERTIES:
            if material[p] and p != "max_service_temp_c":
                yield name, p, material[p]


# ─── geom.DENSITY ────────────────────────────────────────────────────────────

def test_density_is_what_it_always_was_in_the_order_it_was_listed():
    assert geom.DENSITY == LEGACY_DENSITY
    assert list(geom.DENSITY) == list(LEGACY_DENSITY)               # `cad tables density` prints it in order
    assert all(isinstance(v, float) for v in geom.DENSITY.values())


def test_mass_still_comes_from_volume_and_density_and_names_the_materials_it_knows():
    box = Box(10, 20, 30)                                            # 6 cm^3
    assert geom.mass_g(box, " PLA ") == pytest.approx(6.0 * 1.24, rel=1e-12)
    assert geom.mass_g(box, "Aluminum") == geom.mass_g(box, "aluminium")
    with pytest.raises(KeyError) as e:
        geom.mass_g(box, "unobtainium")
    assert str(e.value).strip("'\"") == f"unknown material 'unobtainium'; known: {sorted(LEGACY_DENSITY)}"


# ─── The table ───────────────────────────────────────────────────────────────

def test_every_material_has_the_same_properties_and_a_lower_case_name():
    assert list(MATERIALS) == [k for k in LEGACY_DENSITY if k != "aluminum"]
    for name, material in MATERIALS.items():
        assert name == name.lower() and set(material) == {"card", *PROPERTIES}, name
        assert material["density_g_cm3"], f"{name} has no density, which every mass needs"
    assert materials.ALIASES == {"aluminum": "aluminium"}


def test_values_are_physical():
    for name, p, spec in sources():
        value = spec[0]
        assert isinstance(value, float), (name, p)
        if p == "poisson_ratio":
            assert 0.0 < value < 0.5, (name, value)
        elif p == "density_g_cm3":
            assert 0.8 < value < 22.0, (name, value)
        elif p in ("youngs_modulus_mpa", "yield_strength_mpa"):
            assert 5.0 < value < 1e6, (name, p, value)
    for name, material in MATERIALS.items():
        e, y = material["youngs_modulus_mpa"], material["yield_strength_mpa"]
        assert not (e and y) or y[0] < e[0], f"{name} yields above its modulus"


def test_what_has_no_source_is_none_and_not_a_guess():
    assert materials.prop("fr4", "youngs_modulus_mpa") is None
    assert materials.prop("aluminium", "yield_strength_mpa") is None         # the Generic card gives none
    assert materials.prop("brass", "poisson_ratio") is None
    assert materials.prop("kryptonite", "density_g_cm3") is None


def test_prop_gives_the_value_with_its_source_and_refuses_a_property_it_does_not_have():
    p = materials.prop("Aluminum", "youngs_modulus_mpa")
    assert isinstance(p, Prop) and p.value == 70000.0 and p.source.endswith("YoungsModulus = 70000 MPa")
    assert materials.key("  STEEL ") == "steel" and materials.key("aluminum") == "aluminium"
    assert materials.key("unobtainium") is None and materials.get("unobtainium") is None
    with pytest.raises(KeyError, match="unknown property"):
        materials.prop("steel", "hardness")


# ─── Sources ─────────────────────────────────────────────────────────────────

def test_every_source_is_a_freecad_card_at_the_pinned_commit_or_a_datasheet():
    for name, p, spec in sources():
        assert len(spec) == 2, (name, p)                        # max_service_temp_c, the one with a basis, is not here
        source = spec[1]
        assert CARD_SOURCE.match(source) or SHEET_SOURCE.match(source), (name, p, source)


def test_a_card_gives_the_value_after_the_unit_conversion():
    for name, p, (value, source) in sources():
        m = CARD_SOURCE.match(source)
        if not m:
            continue
        assert m["card"] in CARDS, f"{name}.{p}: {m['card']} is not a card listed in CARDS"
        assert m["key"] == materials.FREECAD_NAMES[p], (name, p, m["key"])
        raw = m["raw"]
        if p == "poisson_ratio":
            assert float(raw) == value, (name, p)
        else:
            (got,) = converted(raw)
            assert got == pytest.approx(value, rel=1e-9), (name, p, raw)


def test_a_datasheet_says_the_number_it_is_cited_for():
    seen = 0
    for name, p, (value, source) in sources():
        m = SHEET_SOURCE.match(source)
        if not m:
            continue
        seen += 1
        what = m["what"]
        if p == "poisson_ratio":
            assert f"{value:g}" in what, (name, p, what)
        else:
            gravity = [float(x) for x in re.findall(r"Specific Gravity\s+(\d+\.?\d*)", what)]
            assert any(c == pytest.approx(value, rel=1e-3) for c in converted(what) + gravity), (name, p, what)
    assert seen >= 14


def test_where_freecads_density_differs_ours_is_cited_to_a_datasheet_not_to_the_card():
    # The cards say these; masses were computed with the values in LEGACY_DENSITY and must not move.
    card_density = {"steel": 7.9, "stainless": 7.8, "abs": 1.06, "nylon": 1.15, "acrylic": 1.16}
    for name, theirs in card_density.items():
        value, source = MATERIALS[name]["density_g_cm3"]
        assert value == LEGACY_DENSITY[name] != theirs
        assert SHEET_SOURCE.match(source) and not CARD_SOURCE.match(source), name


def test_the_cards_are_listed_with_their_licence_and_author_and_all_in_use():
    allowed = {"LGPL-2.1-or-later", "LGPL-2.0-or-later", "CC-BY-3.0"}
    used = {CARD_SOURCE.match(s)["card"] for _, _, (_, s) in sources() if CARD_SOURCE.match(s)}
    assert used == set(CARDS)
    for path, (name, author, licence) in CARDS.items():
        assert path.startswith(("Standard/Metal/", "Standard/Thermoplast/")) and path.endswith(".FCMat")
        assert author and licence in allowed, path
    named = {m["card"] for m in MATERIALS.values() if m["card"]}
    assert named == {name for name, _, _ in CARDS.values()}


# ─── The slot for step 6, piece C1 ───────────────────────────────────────────

def test_max_service_temperature_is_a_slot_that_takes_a_value_a_basis_and_a_datasheet():
    # What it may hold: (value in C, datasheet URL: what it says, basis). Piece C1 filled it; tests/test_heat.py
    # reads each number back against its sheet.
    for name, material in MATERIALS.items():
        slot = material["max_service_temp_c"]
        if slot is None:
            continue
        value, source, basis = slot
        assert -273.0 < value < 3000.0, name
        assert re.match(r"https://\S+: .+", source) and basis in MAX_TEMP_BASES, (name, slot)
        assert materials.prop(name, "max_service_temp_c").basis == basis
    assert MAX_TEMP_BASES == ("HDT ISO 75-2 B", "UL 746B RTI", "Tg", "stated service limit")


def test_nylons_service_temperature_is_a_pa6_sheets_and_not_the_pa66_its_density_cites():
    # The card is FreeCAD's Polyamide 6, and the HDT once cited Zytel 101L, a PA66 (190 C): a different polymer.
    # The density keeps that sheet's 1.14, since every mass rests on it, and says so in the module's docstring.
    value, source, basis = MATERIALS["nylon"]["max_service_temp_c"]
    assert (value, basis) == (180.0, "HDT ISO 75-2 B")
    url, what = source.split(": ", 1)
    assert url == "https://www.protolabs.com/media/tqzke2yx/zytel-7335f-nc010.pdf"
    assert "polyamide 6" in what and "PA66" not in what and "101L" not in what
    assert "0.45 MPa, Unannealed, Dry 180 °C (ISO 75-2/B)" in what
    assert MATERIALS["nylon"]["card"] == "Polyamide 6"
    density, density_source = MATERIALS["nylon"]["density_g_cm3"]
    assert density == LEGACY_DENSITY["nylon"] == 1.14 and "Zytel 101L" in density_source
    assert "PA66" in materials.__doc__ and "1.13" in materials.__doc__          # and the docstring says so


# ─── It is code, so the engine hash covers it ────────────────────────────────

def test_a_change_to_the_table_changes_the_engine_hash_because_it_is_python_source():
    path = Path(materials.__file__)
    assert path.suffix == ".py" and verify.PKG in path.parents
    assert "materials.py" in {p.name for p in verify.PKG.rglob("*.py")}


# ─── cad tables materials ────────────────────────────────────────────────────

def run(capsys, *argv):
    code = cli.main(["--json", *argv])
    out, _ = capsys.readouterr()
    return code, json.loads([ln for ln in out.splitlines() if ln.startswith("{")][-1])


def test_cad_tables_materials_prints_every_value_with_its_source(capsys):
    code, out = run(capsys, "tables", "materials")
    assert code == 0 and list(out["data"]) == ["materials"]
    table = out["data"]["materials"]
    assert list(table) == list(MATERIALS)
    al = table["aluminium"]
    assert al["density_g_cm3"] == 2.7 and al["youngs_modulus_mpa"] == 70000.0 and al["poisson_ratio"] == 0.35
    assert al["yield_strength_mpa"] is None
    assert al["max_service_temp_c"] == 170.0 and al["max_service_temp_basis"] == "stated service limit"
    assert al["sources"]["max_service_temp_c"].startswith("https://www.makeitfrom.com/")
    assert al["aliases"] == ["aluminum"] and al["card"] == "Aluminum Generic"
    assert al["sources"]["density_g_cm3"].startswith(f"FreeCAD {FREECAD_COMMIT} src/Mod/Material/")
    assert "yield_strength_mpa" not in al["sources"]                    # nothing to cite, nothing printed
    assert table["petg"]["sources"]["density_g_cm3"].startswith("https://")


def test_the_other_tables_are_unchanged_and_materials_joins_the_full_listing(capsys):
    code, out = run(capsys, "tables", "density")
    assert code == 0 and out["data"] == {"density_g_cm3": LEGACY_DENSITY}
    code, out = run(capsys, "tables")
    assert {"density_g_cm3", "materials", "clearance_hole_mm"} <= set(out["data"])
    code, out = run(capsys, "tables", "nope")
    assert code == 3 and "materials" in out["data"]["error"]
