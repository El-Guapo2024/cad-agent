"""Each TechDraw object type's properties in a fresh FreeCAD 26.3 (3160daf1e2b6): TypeId, group, value, editor mode,
enumeration items. Run in freecadcmd, OUT naming the file to write (techdrawprops.py reads it):

    OUT=/tmp/fctechdraw_types.json $FREECAD/freecadcmd ui/scripts/fctechdraw_types.py
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
g = doc.addObject("TechDraw::DrawProjGroup", "ProjGroup"); page.addView(g); g.Source = [box]; g.addProjection("Front")
s = doc.addObject("TechDraw::DrawViewSection", "Section"); page.addView(s); s.BaseView = v; s.Source = [box]
d = doc.addObject("TechDraw::DrawViewDimension", "Dimension"); page.addView(d)
b = doc.addObject("TechDraw::DrawViewBalloon", "Balloon"); page.addView(b)
a = doc.addObject("TechDraw::DrawViewAnnotation", "Annotation"); page.addView(a)
doc.recompute()
out = {}
for o in [page, tpl, v, g, doc.getObject("ProjItem"), s, d, b, a]:
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
    out[o.TypeId + ("" if o.Name != "ProjItem" else ":item")] = props
for t in out.values():
    for x in t.values():
        if isinstance(x.get("value"), str) and "/" in x["value"]:
            x["value"] = x["value"].rsplit("/", 1)[-1]          # no local folder in the file
json.dump(out, open(os.environ["OUT"], "w"), indent=1, default=repr)
print("ok", list(out))
