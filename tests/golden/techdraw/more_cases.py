"""The inputs of tests/golden/techdraw/make_more.py (freecadcmd) and tests/test_techdraw_more.py (cad_agent): leader lines made
with TechDraw.makeLeader, symbols with editable texts, a clip group with views added, welds and images, loaded by both by path.
"""

# A leader line on a view at scale 1 and no rotation: DrawLeaderLine::makeLeader's X, Y and WayPoints equal what TaskLeaderLine makes.
LEADERS = [
    {"name": "L1", "view": {"x": 148.5, "y": 105.0}, "points": [[120.0, 100.0], [140.0, 125.0], [170.0, 125.0]], "start": 0, "end": 7},
    {"name": "L2", "view": {"x": 100.0, "y": 90.0}, "points": [[60.0, 60.0], [75.0, 60.0]], "start": 2, "end": 3},
    {"name": "L3", "view": {"x": 148.5, "y": 105.0}, "points": [[130.0, 95.0], [131.5, 99.0], [120.0, 110.0], [100.0, 110.0]], "start": 5, "end": 0},
]

# An SVG with editable texts (what DrawViewSymbol::getEditableFields reads, updateFieldsInSymbol writes)
EDITABLE_SVG = (
    '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
    '<svg xmlns="http://www.w3.org/2000/svg" xmlns:freecad="http://www.freecad.org/wiki/index.php?title=Svg_Namespace" '
    'width="40" height="20" viewBox="0 0 40 20">\n'
    '  <rect x="1" y="1" width="38" height="18" fill="none" stroke="#000"/>\n'
    '  <text x="4" y="8" freecad:editable="first"><tspan>one</tspan></text>\n'
    '  <text x="4" y="16" freecad:editable="second"><tspan>two</tspan></text>\n'
    '  <text x="30" y="16"><tspan>fixed</tspan></text>\n'
    '</svg>\n')
EDITED = ["alpha", "beta & <gamma>"]

# Views put in a clip group (DrawViewClip::addView): the view's X, Y become relative to the clip when its rectangle holds the clip's
# place, and 0, 0 when it does not. The clip is at (148.5, 105); an annotation is a DrawView whose rectangle is its text's.
CLIP_VIEWS = [
    {"kind": "DrawViewAnnotation", "x": 148.5, "y": 105.0, "text": ["clip me"]},
    {"kind": "DrawViewAnnotation", "x": 20.0, "y": 20.0, "text": ["far away"]},
    {"kind": "DrawViewSymbol", "x": 150.0, "y": 107.0},
]

# a weld symbol's tiles (DrawWeldSymbol::onSettingDocument) and a symbol file (DrawTileWeld::replaceFileIncluded)
WELD_SYMBOL_FILES = ["Welding/AWS/filletDown.svg", "Welding/GOST/seam-weld.svg", "Welding/blankTile.svg"]
SYMBOL_FILES = ["misc/North.svg", "other/Diameter.svg"]
