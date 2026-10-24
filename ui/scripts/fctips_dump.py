# Runs inside FreeCAD's GUI for fctips.py: every command's menu text, tooltip and shortcut, and the tooltip each
# toolbar button shows (Action::createToolTip's rich text), to $FCGUI_OUT/fctips.json; then ends the process.
import json
import os
import traceback

import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtCore, QtWidgets

OUT = os.environ["FCGUI_OUT"]
app = QtWidgets.QApplication.instance()
mw = Gui.getMainWindow()


def pump(ms):
    t = QtCore.QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        app.processEvents(QtCore.QEventLoop.AllEvents, 50)


def run():
    res = {"commands": {}, "toolbars": {}}
    try:
        App.newDocument()
        for wb in ["NoneWorkbench", "PartWorkbench", "SketcherWorkbench", "PartDesignWorkbench"]:
            Gui.activateWorkbench(wb)
            pump(800)
            for tb in mw.findChildren(QtWidgets.QToolBar):
                if not tb.isVisible():
                    continue
                res["toolbars"].setdefault(tb.objectName() or tb.windowTitle(), [
                    {"cmd": a.property("CommandName"), "text": a.text(),
                     "tip": (tb.widgetForAction(a) or a).toolTip()}
                    for a in tb.actions() if not a.isSeparator()])
        for n in sorted(Gui.listCommands()):
            try:
                info = Gui.Command.get(n).getInfo()
                res["commands"][n] = {"menu": info.get("menuText"), "tip": info.get("toolTip"),
                                      "shortcut": info.get("shortcut")}
            except Exception as e:  # a command whose module failed to load
                res["commands"][n] = {"error": str(e)}
    except Exception:
        res["error"] = traceback.format_exc()
    with open(os.path.join(OUT, "fctips.json"), "w") as f:
        json.dump(res, f, indent=1, ensure_ascii=False)
    os._exit(0)


QtCore.QTimer.singleShot(3000, run)
