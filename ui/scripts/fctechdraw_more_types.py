"""The properties of the TechDraw objects fctechdraw_types.py does not cover (leader, rich text, symbols, welds, image, clip) in a
fresh FreeCAD 26.3 (3160daf1e2b6): TypeId, group, value, editor mode, enumeration items. Run in freecadcmd, OUT naming the file:

    OUT=/tmp/fctechdraw_more_types.json $FREECAD/freecadcmd ui/scripts/fctechdraw_more_types.py
"""
import json, os
import FreeCAD as App, Part, TechDraw
doc = App.newDocument("t")
box = doc.addObject("Part::Box", "Box")
page = doc.addObject("TechDraw::DrawPage", "Page")
tpl = doc.addObject("TechDraw::DrawSVGTemplate", "Template")
tpl.Template = App.getResourceDir() + "Mod/TechDraw/Templates/Default_Template_A4_Landscape.svg"
page.Template = tpl
v = doc.addObject("TechDraw::DrawProjGroupItem", "View"); page.addView(v); v.Source = [box]
doc.recompute()
ll = doc.addObject("TechDraw::DrawLeaderLine", "LeaderLine"); page.addView(ll); ll.LeaderParent = v
ra = doc.addObject("TechDraw::DrawRichAnno", "RichTextAnnotation"); page.addView(ra)
sy = doc.addObject("TechDraw::DrawViewSymbol", "Symbol"); page.addView(sy)
ws = doc.addObject("TechDraw::DrawWeldSymbol", "WeldSymbol"); page.addView(ws); ws.Leader = ll
im = doc.addObject("TechDraw::DrawViewImage", "Image"); page.addView(im)
cl = doc.addObject("TechDraw::DrawViewClip", "Clip"); page.addView(cl)
doc.recompute()
out = {}
for o in [ll, ra, sy, ws, doc.getObject("TileWeld"), im, cl]:
    props = {}
    for p in o.PropertiesList:
        try:
            val = getattr(o, p)
        except Exception as e:
            val = repr(e)
        if hasattr(val, "x") and hasattr(val, "z"):
            val = [val.x, val.y, val.z]
        elif hasattr(val, "Value") and hasattr(val, "Unit"):
            val = val.Value
        elif isinstance(val, (list, tuple)):
            val = [x.Name if hasattr(x, "Name") else (repr(x) if not isinstance(x, (int, float, str)) else x) for x in val]
        elif hasattr(val, "Name"):
            val = val.Name
        elif not isinstance(val, (int, float, str, bool, type(None), dict)):
            val = repr(val)
        e = None
        try:
            e = o.getEnumerationsOfProperty(p)
        except Exception:
            pass
        props[p] = {"type": o.getTypeIdOfProperty(p), "group": o.getGroupOfProperty(p), "value": val,
                    "mode": o.getEditorMode(p), "doc": o.getDocumentationOfProperty(p), **({"enum": e} if e else {})}
    out[o.TypeId] = props
out["objects"] = [o.Name for o in doc.Objects]
out["labels"] = [o.Label for o in doc.Objects]
for t in out.values():
    if isinstance(t, dict):
        for x in t.values():
            if isinstance(x.get("value"), str) and "/" in x["value"]:
                x["value"] = x["value"].rsplit("/", 1)[-1]
json.dump(out, open(os.environ["OUT"], "w"), indent=1, default=repr)
print("ok", list(out))
