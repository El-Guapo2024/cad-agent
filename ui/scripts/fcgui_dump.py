# Runs inside FreeCAD's GUI (offscreen, started by fcgui.py): dumps what its interface really contains —
# every command's info, the menus and toolbars of three workbenches, docks, status bar — and
# screenshots, as the reference our UI is compared with.
import os, json, traceback
import FreeCAD as App, FreeCADGui as Gui
from PySide import QtGui, QtCore
try:
    from PySide6 import QtWidgets
except ImportError:
    QtWidgets = QtGui
OUT = os.environ["FCGUI_OUT"]
os.makedirs(OUT, exist_ok=True)
mw = Gui.getMainWindow()
app = QtWidgets.QApplication.instance()
res = {"version": App.Version(), "font": [app.font().family(), app.font().pointSizeF(), app.font().pixelSize()],
       "style": app.style().objectName()}


def act(a, depth=0):
    if a.isSeparator():
        return {"sep": True}
    d = {"text": a.text(), "name": a.objectName(), "shortcut": a.shortcut().toString(), "checkable": a.isCheckable(),
         "checked": a.isChecked(), "enabled": a.isEnabled(), "visible": a.isVisible(), "tip": a.toolTip(),
         "status": a.statusTip(), "icon": not a.icon().isNull()}
    m = a.menu()
    if m is not None and depth < 6:
        try:
            m.aboutToShow.emit()
        except Exception:
            pass
        d["menu"] = [act(x, depth + 1) for x in m.actions()]
    return d


def chrome():
    try:
        mb = [act(a) for a in mw.menuBar().actions()]
    except Exception:
        mb = traceback.format_exc()
    tbs = []
    for tb in mw.findChildren(QtWidgets.QToolBar):
        tbs.append({"name": tb.objectName(), "title": tb.windowTitle(), "visible": tb.isVisible(),
                    "area": str(mw.toolBarArea(tb)), "actions": [act(a) for a in tb.actions()]})
    return {"menubar": mb, "toolbars": tbs}


res["commands"] = {}
for name in sorted(Gui.listCommands()):
    try:
        res["commands"][name] = Gui.Command.get(name).getInfo()
    except Exception as e:
        res["commands"][name] = {"error": str(e)}
res["workbenches"] = {}
for wb in ("NoneWorkbench", "PartWorkbench", "PartDesignWorkbench"):
    try:
        Gui.activateWorkbench(wb)
        app.processEvents()
        res["workbenches"][wb] = chrome()
    except Exception:
        res["workbenches"][wb] = traceback.format_exc()
docks = []
for dw in mw.findChildren(QtWidgets.QDockWidget):
    docks.append({"name": dw.objectName(), "title": dw.windowTitle(), "visible": dw.isVisible(), "area": str(mw.dockWidgetArea(dw))})
res["docks"] = docks
sb = mw.statusBar()
res["statusbar"] = [{"class": w.metaObject().className(), "name": w.objectName(), "text": getattr(w, "text", lambda: "")(),
                     "tip": w.toolTip(), "geom": [w.x(), w.y(), w.width(), w.height()], "visible": w.isVisible()}
                    for w in sb.findChildren(QtWidgets.QWidget) if w.parent() is sb]
mw.grab().save(os.path.join(OUT, "start-800.png"))
mw.resize(1280, 800); app.processEvents()
mw.grab().save(os.path.join(OUT, "start-1280.png"))
try:
    doc = App.newDocument("Unnamed")
    box = doc.addObject("Part::Box", "Box")
    doc.recompute()
    app.processEvents()
    Gui.Selection.addSelection(box)
    app.processEvents()   # no more: pumping events lets the GL-less 3D view hang FreeCAD
    mw.grab().save(os.path.join(OUT, "box-1280.png"))
    for dw in mw.findChildren(QtWidgets.QDockWidget):
        if dw.isVisible():
            dw.grab().save(os.path.join(OUT, "dock-%s.png" % (dw.objectName() or "x")))
    res["after_doc"] = chrome()
except Exception:
    res["doc_error"] = traceback.format_exc()
json.dump(res, open(os.path.join(OUT, "freecad-gui.json"), "w"), ensure_ascii=False)
os._exit(0)
