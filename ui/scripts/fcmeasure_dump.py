# Runs inside FreeCAD's GUI (fcmeasure.py starts it on the cocoa platform, windows kept off the screen): the numbers of the real
# widgets and the colours of a selected Part, for the quick look fixes of the workbench. Writes fcmeasure.json into FCGUI_OUT, and
# freecad-sel-<state>.png (the 3D view without its margins) for each state of the selection experiment.
#
#   widgets    the fonts (the application's, the fixed font, the tooltip's), the toolbars and their tool buttons, the docks and their
#              size hints, the tree and the property view (row heights, columns), the tab bars and every tab's rectangle, the status
#              bar, the 3D view and the Report view (its font, margins and background): QWidget::geometry, as FreeCAD lays them out
#   prefs      what a fresh profile holds for the parameters the comparison cares about (NewDocumentCameraOrientation is unset)
#   selection  a box, a cylinder and a sphere in the isometric view: none, all selected, one preselected, selected and preselected,
#              and a face selected: the ten most common colours of each (the SelectionColor of a whole object is drawn as
#              #11ffff, its HighlightColor as #19b5df on a face of the box, a selected face as #119ddf)
import json
import os
import time
import traceback
from collections import Counter

import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtCore, QtGui, QtOpenGLWidgets, QtWidgets

OUT = os.environ["FCGUI_OUT"]
mw = Gui.getMainWindow()
app = QtWidgets.QApplication.instance()
res = {"errors": {}}
T0 = time.time()


def pump(sec=0.3):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents(QtCore.QEventLoop.AllEvents, 50)
        time.sleep(0.005)


def finish():
    res["done"] = True
    json.dump(res, open(os.path.join(OUT, "fcmeasure.json"), "w"), indent=1)
    os._exit(0)


def watchdog():
    """A step that blocks ends the run with what was measured so far."""
    if time.time() - T0 > 150:
        res["errors"]["hung"] = "no result in 150 s"
        finish()


_wd = QtCore.QTimer()
_wd.timeout.connect(watchdog)
_wd.start(1000)


def safe(name, fn):
    try:
        res[name] = fn()
    except Exception:
        res["errors"][name] = traceback.format_exc()


def rect(w):
    p = w.mapTo(mw, QtCore.QPoint(0, 0))
    return [p.x(), p.y(), w.width(), w.height()]


def font_info(f):
    fm = QtGui.QFontMetrics(f)
    return {"family": f.family(), "pointSize": f.pointSize(), "bold": f.bold(), "height": fm.height(), "lineSpacing": fm.lineSpacing(),
            "ascent": fm.ascent(), "descent": fm.descent(), "advance0": fm.horizontalAdvance("0")}


def by_class(cls, name):
    return [w for w in mw.findChildren(cls) if w.metaObject().className() == name]


mw.resize(1280, 800)
pump(1.5)
doc = App.newDocument("measure")
for name, (x, y, z) in (("Box", (100, 60, 40)),):
    o = doc.addObject("Part::Box", name)
    o.Length, o.Width, o.Height = x, y, z
cyl = doc.addObject("Part::Cylinder", "Cyl")
cyl.Radius, cyl.Height = 20, 60
cyl.Placement = App.Placement(App.Vector(160, 30, 0), App.Rotation())
sph = doc.addObject("Part::Sphere", "Sph")
sph.Radius = 30
sph.Placement = App.Placement(App.Vector(60, -70, 30), App.Rotation())
doc.recompute()
view = Gui.ActiveDocument.ActiveView
view.setAnimationEnabled(False)
view.viewIsometric()
view.fitAll()
Gui.Selection.addSelection(doc.Name, "Box")
pump(1.5)

# ── widgets ─────────────────────────────────────────────────────────────────────────────
safe("fonts", lambda: {"app": font_info(QtGui.QGuiApplication.font()), "fixed": font_info(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)),
                       "tooltip": font_info(QtWidgets.QToolTip.font())})
safe("palette", lambda: {k: QtWidgets.QApplication.palette().color(getattr(QtGui.QPalette, k)).name() for k in ("Window", "Base", "Text", "Highlight", "Mid", "Dark")})
safe("window", lambda: [mw.width(), mw.height()])
safe("menubar", lambda: {"native": mw.menuBar().isNativeMenuBar(), "visible": mw.menuBar().isVisible()})
safe("docks", lambda: {d.objectName() or d.windowTitle(): {"rect": rect(d), "visible": d.isVisible(), "minW": d.minimumWidth(), "sizeHint": [d.sizeHint().width(), d.sizeHint().height()]}
                       for d in mw.findChildren(QtWidgets.QDockWidget)})
safe("toolbars", lambda: {t.objectName(): {"rect": rect(t), "iconSize": [t.iconSize().width(), t.iconSize().height()],
                                           "buttons": [[b.width(), b.height()] for b in t.findChildren(QtWidgets.QToolButton)[:4]]}
                          for t in mw.findChildren(QtWidgets.QToolBar) if t.isVisible()})


def tree():
    t = by_class(QtWidgets.QTreeWidget, "Gui::TreeWidget")[0]
    d = t.topLevelItem(0)
    r = lambda item: [t.visualItemRect(item).x(), t.visualItemRect(item).y(), t.visualItemRect(item).width(), t.visualItemRect(item).height()]
    return {"rect": rect(t), "rowH": t.visualItemRect(d.child(0)).height(), "indent": t.indentation(), "docRow": r(d), "itemRow": r(d.child(0)),
            "docFontBold": d.font(0).bold(), "headerHidden": t.isHeaderHidden()}


safe("tree", tree)


def props():
    p = by_class(QtWidgets.QTreeView, "Gui::PropertyEditor::PropertyEditor")[0]
    return {"rect": rect(p), "col0": p.header().sectionSize(0), "indent": p.indentation(), "alternating": p.alternatingRowColors(), "headerHidden": p.isHeaderHidden()}


safe("props", props)
safe("combo", lambda: {"rect": rect(by_class(QtWidgets.QWidget, "Gui::DockWnd::ComboView")[0]),
                       "splitterSizes": by_class(QtWidgets.QWidget, "Gui::DockWnd::ComboView")[0].findChildren(QtWidgets.QSplitter)[0].sizes()})
safe("tabs", lambda: [{"name": t.objectName(), "rect": rect(t), "closable": t.tabsClosable(),
                       "tabs": [[t.tabText(i), t.tabRect(i).x(), t.tabRect(i).y(), t.tabRect(i).width(), t.tabRect(i).height()] for i in range(t.count())]}
                      for t in mw.findChildren(QtWidgets.QTabBar) if t.isVisible()])
safe("statusbar", lambda: rect(mw.statusBar()))
safe("view3d", lambda: [rect(w) for w in mw.findChildren(QtOpenGLWidgets.QOpenGLWidget) if w.width() > 300][0])

dw = [d for d in mw.findChildren(QtWidgets.QDockWidget) if d.windowTitle() == "Report view"]
if dw:
    dw[0].show()
    pump(0.8)
    App.Console.PrintMessage("Opened measure\n")
    App.Console.PrintWarning("a warning\n")
    App.Console.PrintError("an error\n")
    pump(0.8)


def report():
    r = by_class(QtWidgets.QTextEdit, "Gui::DockWnd::ReportOutput")[0]
    return {"font": font_info(r.font()), "documentMargin": r.document().documentMargin(), "background": r.viewport().palette().color(QtGui.QPalette.Base).name()}


safe("report", report)
safe("prefs", lambda: {
    "OutputWindow": {k: "#%08x" % App.ParamGet("User parameter:BaseApp/Preferences/OutputWindow").GetUnsigned(k, 0)
                     for k in ("colorText", "colorLogging", "colorWarning", "colorError")},
    "Editor": {"FontSize": App.ParamGet("User parameter:BaseApp/Preferences/Editor").GetInt("FontSize", -1),
               "Font": App.ParamGet("User parameter:BaseApp/Preferences/Editor").GetString("Font", "<unset>")},
    "View": {"NewDocumentCameraOrientation": App.ParamGet("User parameter:BaseApp/Preferences/View").GetString("NewDocumentCameraOrientation", "<unset>"),
             "SelectionColor": "#%08x" % App.ParamGet("User parameter:BaseApp/Preferences/View").GetUnsigned("SelectionColor", 0),
             "HighlightColor": "#%08x" % App.ParamGet("User parameter:BaseApp/Preferences/View").GetUnsigned("HighlightColor", 0),
             "HeadlightColor": "#%08x" % App.ParamGet("User parameter:BaseApp/Preferences/View").GetUnsigned("HeadlightColor", 0)}})

# ── selection ───────────────────────────────────────────────────────────────────────────
w3 = [w for w in mw.findChildren(QtOpenGLWidgets.QOpenGLWidget) if w.width() > 300][0]
p3 = w3.mapTo(mw, QtCore.QPoint(0, 0))
region = (p3.x() + 20, p3.y() + 20, w3.width() - 40, w3.height() - 40)
res["selection"] = {}


def grab(name):
    pump(0.6)
    img = mw.grab().copy(*region)
    img.save(os.path.join(OUT, "freecad-sel-%s.png" % name))
    q = img.toImage() if hasattr(img, "toImage") else img
    c = Counter(q.pixel(x, y) & 0xFFFFFF for y in range(0, q.height(), 2) for x in range(0, q.width(), 2))
    tot = sum(c.values())
    res["selection"][name] = [["#%06x" % k, round(100.0 * n / tot, 2)] for k, n in c.most_common(10)]


def state(name, fn):
    try:
        fn()
        grab(name)
    except Exception:
        res["errors"]["selection-" + name] = traceback.format_exc()


def clear():
    Gui.Selection.clearSelection()


def sel_all():
    clear()
    for o in ("Box", "Cyl", "Sph"):
        Gui.Selection.addSelection(doc.Name, o)


def pre_box():
    clear()
    Gui.Selection.setPreselection(doc.getObject("Box"), "", 50, 30, 40, 1)


def sel_and_pre():
    clear()
    Gui.Selection.addSelection(doc.Name, "Box")
    Gui.Selection.setPreselection(doc.getObject("Box"), "", 50, 30, 40, 1)


def face():
    clear()
    Gui.Selection.addSelection(doc.Name, "Box", "Face6")


state("none", clear)
state("selected", sel_all)
state("preselected", pre_box)
state("selected-and-preselected", sel_and_pre)
state("face-selected", face)
finish()
