# SPDX-License-Identifier: LGPL-2.1-or-later
# Runs inside FreeCAD's GUI (navishots.py starts it): grabs the 3D view, NaviCube and all, at the orientations and pointer
# positions of navishots_ours.mjs, as FCGUI_OUT/fc-<shot>.png. The 3D view is drawn by OpenGL, so on Linux under Xvfb
# (Mesa's llvmpipe) the cube looks as it does anywhere: its look does not depend on the platform's Qt style.
import json
import math
import os
import time
import traceback

import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtCore, QtGui, QtOpenGLWidgets, QtTest, QtWidgets

OUT = os.environ["FCGUI_OUT"]
SHOTS = json.loads(os.environ["NAVI_SHOTS"])  # {"orient": {name: [x, y, z, w] | "persp"}, "hover": {name: [dx, dy]}}
app = QtWidgets.QApplication.instance()
mw = Gui.getMainWindow()
res = {}


def pump(sec=0.4):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents(QtCore.QEventLoop.AllEvents, 50)
        time.sleep(0.005)


try:
    mw.resize(1280, 800)
    mw.show()
    pump(1.5)
    App.newDocument("navi")
    pump(1.0)
    view = Gui.ActiveDocument.ActiveView
    gl = sorted((w for w in mw.findChildren(QtOpenGLWidgets.QOpenGLWidget) if w.isVisible()), key=lambda w: -w.width() * w.height())
    w3 = gl[0]
    W, H = w3.width(), w3.height()
    res["view3d"] = [W, H, w3.devicePixelRatioF()]

    def grab(name):
        pump(0.6)
        w3.grabFramebuffer().save(os.path.join(OUT, "fc-%s.png" % name))

    def move(x, y):
        # QTest moves the cursor there too; the event is what the viewer reads.
        QtTest.QTest.mouseMove(w3, QtCore.QPoint(int(x), int(y)))
        p = QtCore.QPointF(x, y)
        app.sendEvent(w3, QtGui.QMouseEvent(QtCore.QEvent.MouseMove, p, p, QtCore.Qt.NoButton, QtCore.Qt.NoButton, QtCore.Qt.NoModifier))
        pump(0.3)

    # The cube's centre: posAreaBase is int(OffsetX 0 + 132 * 0.55) = 72 from the top right corner (NaviCube.cpp handleResize).
    cx, cy = W - 72, 72
    for name, q in SHOTS["orient"].items():
        if q == "persp":
            view.viewIsometric()
            view.setCameraType("Perspective")
        else:
            n = math.sqrt(sum(c * c for c in q))
            view.setCameraOrientation(tuple(c / n for c in q))
        pump(1.2)
        move(W / 2, H / 2)
        grab(name + "-away")
        move(cx, cy)
        grab(name + "-near")
        if q == "persp":
            view.setCameraType("Orthographic")
    view.viewIsometric()
    pump(1.0)
    for name, (dx, dy) in SHOTS["hover"].items():
        move(cx + dx, cy + dy)
        grab(name)
except Exception:
    res["error"] = traceback.format_exc()
json.dump(res, open(os.path.join(OUT, "fc.json"), "w"), indent=1)
os._exit(0)
