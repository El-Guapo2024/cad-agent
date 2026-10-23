# The real FreeCAD's arrow-key pan step (SoQTQuarterAdaptor::processSoEvent), at several view sizes.
# Run under a display, writing JSON to $ARROW_OUT:
#   ARROW_OUT=out.json HOME=$(mktemp -d) xvfb-run -a -s "-screen 0 3000x2000x24" freecad ui/scripts/arrowpan_fc.py
# Each row is one press of Right or Up, as a fraction of the visible width and height (measured with
# getPointOnFocalPlane, so no model of Coin's view volume goes in). navcheck.mjs holds the answers.
import FreeCAD as App, FreeCADGui as Gui, json, os
from PySide import QtCore, QtGui, QtWidgets
def cf(iv):
    f = {}
    for line in iv.splitlines():
        p = line.split()
        if len(p) > 1:
            try: f[p[0]] = [float(x) for x in p[1:]]
            except ValueError: pass
    return f
out = os.environ["ARROW_OUT"]
def run():
    res = []
    try:
        mw = Gui.getMainWindow(); mdi = mw.findChild(QtWidgets.QMdiArea)
        mdi.setViewMode(QtWidgets.QMdiArea.SubWindowView)
        App.newDocument("A"); Gui.activeDocument().activeView().viewIsometric()
        v = Gui.ActiveDocument.ActiveView
        sub = mdi.subWindowList()[0]; sub.showNormal()
        gv = v.graphicsView()
        for cam in ("Orthographic", "Perspective"):
            v.setCameraType(cam)
            for W, H in [(800, 600), (1000, 450), (1700, 800), (2100, 700), (500, 800), (300, 900), (600, 600)]:
                mw.resize(W + 600, H + 600); sub.setFixedSize(W + 40, H + 60); gv.setFixedSize(W, H)
                for _ in range(20): QtWidgets.QApplication.processEvents()
                gw, gh = gv.viewport().width(), gv.viewport().height()
                for key, name in [(QtCore.Qt.Key_Right, "right"), (QtCore.Qt.Key_Up, "up")]:
                    c = cf(v.getCamera())
                    p0 = App.Vector(*c["position"])
                    gv.setFocus()
                    for t in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease):
                        QtWidgets.QApplication.sendEvent(gv.viewport(), QtGui.QKeyEvent(t, key, QtCore.Qt.NoModifier))
                    for _ in range(5): QtWidgets.QApplication.processEvents()
                    c = cf(v.getCamera()); p1 = App.Vector(*c["position"])
                    d = p1 - p0
                    if cam == "Orthographic":
                        Hc = c["height"][0]
                    else:
                        import math
                        Hc = 2 * c["focalDistance"][0] * math.tan(c["heightAngle"][0] / 2)
                    a = gw / gh
                    P = lambda x, y: App.Vector(*v.getPointOnFocalPlane(x, y))
                    vis_w = (P(gw, gh // 2) - P(0, gh // 2)).Length
                    vis_h = (P(gw // 2, gh) - P(gw // 2, 0)).Length
                    res.append(dict(cam=cam, w=gw, h=gh, key=name, move=d.Length,
                                    frac_w=d.Length / vis_w, frac_h=d.Length / vis_h))
    except Exception as e:
        import traceback; res.append(dict(error=traceback.format_exc()))
    open(out, "w").write(json.dumps(res, indent=1))
    QtWidgets.QApplication.quit()
QtCore.QTimer.singleShot(3000, run)
