# Runs inside FreeCAD's GUI (fcprefs.py starts it on the cocoa platform, windows kept off the screen): every Preferences page the
# workbench has, as the real dialog lays it out, for the side-by-side with the workbench (oursprefs.mjs reads the same things off ours).
# Writes into FCGUI_OUT: freecad-prefs-<page>.png (the dialog as grabbed, the page in full: the dialog is made tall enough that the
# page does not scroll), and fcprefs.json:
#   dialog   the dialog's size and metrics (the sidebar, the tree rows, the header, the search box, the buttons and their order)
#   pages    per page: its rectangle and, for every widget in it, the class, object name, the text it shows, its rectangle in the
#            page's coordinates, enabled and visible, the value it shows after loadSettings() in this fresh profile (checked, value,
#            current text, colour, ...), its tool tip, its size policy and size hints, and the preference it is bound to; and every
#            layout with its margins, spacing and items (row, column, spans, alignment, stretch)
# Nothing is clicked or typed: the pages are selected from a timer inside the modal dialog's event loop, as fcshots_dump.py does.
import json
import os
import time
import traceback

import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtCore, QtGui, QtWidgets

OUT = os.environ["FCGUI_OUT"]
ONLY = set(filter(None, os.environ.get("FCPREFS_ONLY", "").split(",")))
TALL = int(os.environ.get("FCPREFS_TALL", "1900"))
mw = Gui.getMainWindow()
app = QtWidgets.QApplication.instance()
res = {"errors": {}, "pages": {}, "dialog": {}}
T0 = time.time()
LAST = [time.time(), "start"]

# the pages the workbench has: the class FreeCAD registers each under, and the key ours uses (resource.cpp's order within a group)
PAGES = [
    ("General", "Gui::Dialog::DlgSettingsGeneral", "general"),
    ("General", "Gui::Dialog::DlgSettingsDocumentImp", "document"),
    ("General", "Gui::Dialog::DlgSettingsSelection", "selection"),
    ("General", "Gui::Dialog::DlgCustomKeyboardImp", "keyboard"),
    ("General", "Gui::Dialog::DlgSettingsCacheDirectory", "cache"),
    ("General", "Gui::Dialog::DlgSettingsNotificationArea", "notificationarea"),
    ("General", "Gui::Dialog::DlgSettingsReportView", "reportview"),
    ("Display", "Gui::Dialog::DlgSettings3DViewImp", "3dview"),
    ("Display", "Gui::Dialog::DlgSettingsLightSources", "lightsources"),
    ("Display", "Gui::Dialog::DlgSettingsUI", "ui"),
    ("Display", "Gui::Dialog::DlgSettingsNavigation", "navigation"),
    ("Display", "Gui::Dialog::DlgSettingsViewColor", "colors"),
    ("Display", "Gui::Dialog::DlgSettingsAdvanced", "advanced"),
    ("Workbenches", "Gui::Dialog::DlgSettingsWorkbenchesImp", "workbenches"),
    ("Import-Export", "Gui::Dialog::DlgSettingsPDF", "pdf"),
    ("Python", "Gui::Dialog::DlgSettingsMacroImp", "macro"),
    ("Python", "Gui::Dialog::DlgSettingsPythonConsole", "pythongeneral"),
    ("Python", "Gui::Dialog::DlgSettingsEditor", "editor"),
]


def progress(what):
    LAST[0], LAST[1] = time.time(), what
    with open(os.path.join(OUT, "fcprefs.log"), "a") as f:
        f.write("%.1f %s\n" % (time.time() - T0, what))


def finish():
    res["done"] = True
    json.dump(res, open(os.path.join(OUT, "fcprefs.json"), "w"), indent=1)
    os._exit(0)


def watchdog():
    if time.time() - LAST[0] > float(os.environ.get("FCPREFS_STEP_TIMEOUT", "60")):
        res["errors"]["hung"] = "no progress for 60 s in step %r" % LAST[1]
        finish()


_wd = QtCore.QTimer()
_wd.timeout.connect(watchdog)
_wd.start(1000)


def pump(sec=0.3):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents(QtCore.QEventLoop.AllEvents, 50)
        time.sleep(0.005)


def cname(o):
    return o.metaObject().className()


def rect_in(w, root):
    p = w.mapTo(root, QtCore.QPoint(0, 0))
    return [p.x(), p.y(), w.width(), w.height()]


def size(s):
    return [s.width(), s.height()]


def policy(sp):
    return [str(sp.horizontalPolicy()).split(".")[-1], str(sp.verticalPolicy()).split(".")[-1], sp.horizontalStretch(), sp.verticalStretch()]


def align(a):
    v = int(a.value) if hasattr(a, "value") else int(a)
    out = []
    for name, bit in (("left", 1), ("right", 2), ("hcenter", 4), ("justify", 8), ("top", 32), ("bottom", 64), ("vcenter", 128)):
        if v & bit:
            out.append(name)
    return out


def font_info(f):
    return {"family": f.family(), "pt": f.pointSizeF(), "px": f.pixelSize(), "bold": f.bold(), "weight": int(f.weight().value) if hasattr(f.weight(), "value") else int(f.weight())}


def color_name(c):
    return "#%02x%02x%02x%02x" % (c.alpha(), c.red(), c.green(), c.blue())


def value_of(w):
    """What the widget shows: the state a person reads off it."""
    v = {}
    if isinstance(w, QtWidgets.QGroupBox):
        v.update(title=w.title(), checkable=w.isCheckable(), checked=w.isChecked(), flat=w.isFlat())
    elif isinstance(w, QtWidgets.QLabel):
        v.update(text=w.text(), wordWrap=w.wordWrap(), alignment=align(w.alignment()), textFormat=str(w.textFormat()).split(".")[-1],
                 buddy=w.buddy().objectName() if w.buddy() else None, openLinks=w.openExternalLinks(), hasPixmap=bool(w.pixmap() and not w.pixmap().isNull()))
    elif isinstance(w, QtWidgets.QAbstractButton):
        v.update(text=w.text(), checkable=w.isCheckable(), checked=w.isChecked())
        if isinstance(w, QtWidgets.QPushButton):
            v.update(default=w.isDefault(), autoDefault=w.autoDefault(), flat=w.isFlat(), hasIcon=not w.icon().isNull())
        if isinstance(w, QtWidgets.QToolButton):
            v.update(hasIcon=not w.icon().isNull(), iconSize=size(w.iconSize()))
        c = w.property("color")
        if c is not None and isinstance(c, QtGui.QColor):
            v.update(color=color_name(c), allowTransparency=w.property("allowTransparency"))
    elif isinstance(w, QtWidgets.QComboBox):
        v.update(currentText=w.currentText(), currentIndex=w.currentIndex(), count=w.count(), editable=w.isEditable(),
                 items=[w.itemText(i) for i in range(min(w.count(), 80))], maxVisible=w.maxVisibleItems())
    elif isinstance(w, QtWidgets.QAbstractSpinBox):
        le = w.lineEdit()
        v.update(text=le.text() if le else "", alignment=align(w.alignment()), readOnly=w.isReadOnly(), buttons=str(w.buttonSymbols()).split(".")[-1])
        for name in ("value", "minimum", "maximum", "singleStep", "suffix", "prefix", "decimals", "specialValueText"):
            if hasattr(w, name):
                try:
                    x = getattr(w, name)()
                    v[name] = x if isinstance(x, (int, float, str, bool)) else str(x)
                except Exception:
                    pass
    elif isinstance(w, QtWidgets.QLineEdit):
        v.update(text=w.text(), placeholder=w.placeholderText(), readOnly=w.isReadOnly(), echo=str(w.echoMode()).split(".")[-1])
    elif isinstance(w, QtWidgets.QTextEdit):
        v.update(text=w.toPlainText()[:200], readOnly=w.isReadOnly())
    elif isinstance(w, QtWidgets.QSlider):
        v.update(value=w.value(), minimum=w.minimum(), maximum=w.maximum())
    elif isinstance(w, QtWidgets.QTableWidget):
        v.update(rows=w.rowCount(), cols=w.columnCount(),
                 headers=[w.horizontalHeaderItem(c).text() if w.horizontalHeaderItem(c) else "" for c in range(w.columnCount())],
                 colWidths=[w.columnWidth(c) for c in range(w.columnCount())], rowHeights=[w.rowHeight(r) for r in range(min(w.rowCount(), 12))],
                 headerHeight=w.horizontalHeader().height(), hHeaderVisible=w.horizontalHeader().isVisible(), vHeaderVisible=w.verticalHeader().isVisible(),
                 cells=[[w.item(r, c).text() if w.item(r, c) else None for c in range(w.columnCount())] for r in range(min(w.rowCount(), 30))],
                 grid=w.showGrid(), alternating=w.alternatingRowColors())
    elif isinstance(w, QtWidgets.QTreeWidget):
        hi = w.headerItem()
        v.update(columns=w.columnCount(), headers=[hi.text(c) for c in range(w.columnCount())] if hi else [], headerHidden=w.isHeaderHidden(),
                 top=w.topLevelItemCount(), rootDecorated=w.rootIsDecorated(), alternating=w.alternatingRowColors(),
                 colWidths=[w.columnWidth(c) for c in range(w.columnCount())], indentation=w.indentation(),
                 rows=[[w.topLevelItem(i).text(c) for c in range(w.columnCount())] for i in range(min(w.topLevelItemCount(), 40))],
                 rowRects=[[w.visualItemRect(w.topLevelItem(i)).x(), w.visualItemRect(w.topLevelItem(i)).y(), w.visualItemRect(w.topLevelItem(i)).width(),
                            w.visualItemRect(w.topLevelItem(i)).height()] for i in range(min(w.topLevelItemCount(), 6))])
    elif isinstance(w, QtWidgets.QListWidget):
        v.update(count=w.count(), items=[w.item(i).text() for i in range(min(w.count(), 60))], alternating=w.alternatingRowColors())
    return v


def layout_info(lay, root):
    d = {"cls": cname(lay), "name": lay.objectName(), "margins": list(lay.getContentsMargins()), "spacing": lay.spacing(),
         "constraint": str(lay.sizeConstraint()).split(".")[-1], "items": []}
    if isinstance(lay, QtWidgets.QGridLayout):
        d["rowStretch"] = [lay.rowStretch(r) for r in range(lay.rowCount())]
        d["columnStretch"] = [lay.columnStretch(c) for c in range(lay.columnCount())]
        d["columnMin"] = [lay.columnMinimumWidth(c) for c in range(lay.columnCount())]
        d["hSpacing"], d["vSpacing"] = lay.horizontalSpacing(), lay.verticalSpacing()
    for i in range(lay.count()):
        it = lay.itemAt(i)
        e = {"align": align(it.alignment())}
        g = it.geometry()
        e["geom"] = [g.x(), g.y(), g.width(), g.height()]
        if isinstance(lay, QtWidgets.QGridLayout):
            e["pos"] = list(lay.getItemPosition(i))
        if it.widget():
            e["widget"] = it.widget().objectName() or cname(it.widget())
        elif it.layout():
            e["layout"] = layout_info(it.layout(), root)
        elif it.spacerItem():
            sp = it.spacerItem()
            e["spacer"] = {"hint": size(sp.sizeHint()), "policy": policy(sp.sizePolicy()) if hasattr(sp, "sizePolicy") else None,
                           "min": size(sp.minimumSize()), "max": size(sp.maximumSize()),
                           "expanding": [str(x).split(".")[-1] for x in sp.expandingDirections()] if hasattr(sp.expandingDirections(), "__iter__") else str(sp.expandingDirections())}
        d["items"].append(e)
    return d


def skip(w, page):
    """The widgets inside another widget (a spin box's line edit, a table's viewport, a combo's list) are not the page's own."""
    n = w.objectName()
    if n.startswith("qt_"):
        return True
    p = w.parentWidget()
    while p is not None and p is not page:
        if isinstance(p, (QtWidgets.QAbstractSpinBox, QtWidgets.QComboBox, QtWidgets.QAbstractScrollArea, QtWidgets.QAbstractButton)):
            return True
        p = p.parentWidget()
    return False


def dump_page(page):
    info = {"cls": cname(page), "title": page.windowTitle(), "rect": [0, 0, page.width(), page.height()], "minSizeHint": size(page.minimumSizeHint()),
            "sizeHint": size(page.sizeHint()), "widgets": [], "layouts": []}
    for w in page.findChildren(QtWidgets.QWidget):
        if skip(w, page):
            continue
        d = {"cls": cname(w), "name": w.objectName(), "rect": rect_in(w, page), "enabled": w.isEnabled(), "visible": w.isVisibleTo(page),
             "tip": w.toolTip(), "policy": policy(w.sizePolicy()), "min": size(w.minimumSize()), "max": size(w.maximumSize()),
             "hint": size(w.sizeHint()), "minHint": size(w.minimumSizeHint()), "font": font_info(w.font()), "focus": str(w.focusPolicy()).split(".")[-1]}
        d["parent"] = w.parentWidget().objectName() or cname(w.parentWidget())
        for prop in ("prefEntry", "prefPath"):
            x = w.property(prop)
            if x:
                d[prop] = str(x)
        d.update(value_of(w))
        info["widgets"].append(d)
    for w in [page] + [x for x in page.findChildren(QtWidgets.QWidget) if not skip(x, page)]:
        lay = w.layout()
        if lay is not None:
            info["layouts"].append({"owner": w.objectName() or cname(w), "layout": layout_info(lay, page)})
    return info


def data_name(item, col):
    v = item.data(col, QtCore.Qt.UserRole)
    if v is None:
        return ""
    try:
        return bytes(v).decode()
    except Exception:
        return str(v)


def extras(key, page, dlg):
    """What a page shows only after something is done to it, read the way a person would reach it: every category of the Keyboard page with
    the commands it lists, the Colors page with a gradient chosen, the Available Workbenches rows with what each holds."""
    out = {}
    if key == "keyboard":
        cb = page.findChild(QtWidgets.QComboBox, "categoryBox")
        tree = page.findChild(QtWidgets.QTreeWidget, "commandTreeWidget")
        cats = {}
        for i in range(cb.count()):
            cb.setCurrentIndex(i)
            cb.activated.emit(i)
            pump(0.25)
            rows = []
            for r in range(tree.topLevelItemCount()):
                it = tree.topLevelItem(r)
                rows.append({"name": data_name(it, 1), "text": it.text(1), "shortcut": it.text(2), "default": it.text(3), "icon": not it.icon(0).isNull()})
            cats[cb.itemText(i)] = {"group": data_name_combo(cb, i), "rows": rows}
        out["categories"] = cats
        cb.setCurrentIndex(0)
        cb.activated.emit(0)
        pump(0.3)
    elif key == "colors":
        states = {}
        for rb, tag, mid in (("radioButtonGradient", "gradient", False), ("rbRadialGradient", "radial", False), ("radioButtonGradient", "gradient-mid", True)):
            btn = page.findChild(QtWidgets.QRadioButton, rb)
            btn.setChecked(True)
            page.findChild(QtWidgets.QCheckBox, "checkMidColor").setChecked(mid)
            pump(0.5)
            states[tag] = dump_page(page)
        page.findChild(QtWidgets.QCheckBox, "checkMidColor").setChecked(False)
        page.findChild(QtWidgets.QRadioButton, "radioButtonSimple").setChecked(True)
        pump(0.3)
        out["states"] = states
    elif key == "workbenches":
        lst = page.findChild(QtWidgets.QListWidget, "wbList")
        rows = []
        for r in range(lst.count()):
            it = lst.item(r)
            w = lst.itemWidget(it)
            rr = lst.visualItemRect(it)
            row = {"rect": [rr.x(), rr.y(), rr.width(), rr.height()], "hint": size(it.sizeHint())}
            if w is not None:
                row["children"] = [{"cls": cname(c), "name": c.objectName(), "rect": rect_in(c, w), "text": c.text() if hasattr(c, "text") else "", "checked": c.isChecked() if hasattr(c, "isChecked") else None,
                                    "enabled": c.isEnabled(), "font": font_info(c.font()), "tip": c.toolTip()} for c in w.findChildren(QtWidgets.QWidget) if not c.objectName().startswith("qt_")]
            rows.append(row)
        out["rows"] = rows
        combo = page.findChild(QtWidgets.QComboBox, "AutoloadModuleCombo")
        out["autoload"] = [{"text": combo.itemText(i), "icon": not combo.itemIcon(i).isNull()} for i in range(combo.count())]
    return out


def data_name_combo(cb, i):
    v = cb.itemData(i, QtCore.Qt.UserRole)
    try:
        return bytes(v).decode()
    except Exception:
        return str(v)


def dump_dialog(dlg, tv):
    d = {"size": size(dlg.size()), "minimum": size(dlg.minimumSize()), "title": dlg.windowTitle(), "sizeGrip": dlg.isSizeGripEnabled()}
    sb = dlg.findChild(QtWidgets.QFrame, "sidebar")
    if sb:
        d["sidebar"] = {"rect": rect_in(sb, dlg), "min": size(sb.minimumSize()), "max": size(sb.maximumSize()), "bg": sb.palette().color(QtGui.QPalette.Window).name(), "style": sb.styleSheet()}
    d["tree"] = {"rect": rect_in(tv, dlg), "iconSize": size(tv.iconSize()), "indentation": tv.indentation(), "headerHidden": tv.isHeaderHidden(), "font": font_info(tv.font())}
    m = tv.model()
    rows = []

    def walk(parent, depth):
        for r in range(m.rowCount(parent)):
            i = m.index(r, 0, parent)
            vr = tv.visualRect(i)
            rows.append({"text": m.data(i), "depth": depth, "rect": [vr.x(), vr.y(), vr.width(), vr.height()], "expanded": tv.isExpanded(i),
                         "hasChildren": m.rowCount(i) > 0, "hasIcon": not (m.data(i, QtCore.Qt.DecorationRole) is None), "visible": vr.isValid() and not vr.isEmpty()})
            walk(i, depth + 1)

    walk(QtCore.QModelIndex(), 0)
    d["tree"]["rows"] = rows
    for name in ("headerLabel", "searchBox", "scrollArea", "buttonBox", "buttonReset", "groupWidgetStack", "verticalFrame"):
        w = dlg.findChild(QtWidgets.QWidget, name)
        if w:
            d[name] = {"rect": rect_in(w, dlg), "font": font_info(w.font()), "min": size(w.minimumSize()), "max": size(w.maximumSize())}
            if isinstance(w, QtWidgets.QLabel):
                d[name]["text"] = w.text()
            if isinstance(w, QtWidgets.QLineEdit):
                d[name]["placeholder"] = w.placeholderText()
                d[name]["clearButton"] = w.isClearButtonEnabled()
    bb = dlg.findChild(QtWidgets.QDialogButtonBox, "buttonBox")
    if bb:
        d["buttons"] = [{"text": b.text(), "rect": rect_in(b, dlg), "default": b.isDefault(), "enabled": b.isEnabled()} for b in bb.buttons()]
        d["buttonOrder"] = [b.text() for b in sorted(bb.buttons(), key=lambda b: b.x())]
    sa = dlg.findChild(QtWidgets.QScrollArea, "scrollArea")
    if sa:
        d["scrollArea"]["vbar"] = {"visible": sa.verticalScrollBar().isVisible(), "w": sa.verticalScrollBar().width()}
        d["scrollArea"]["viewport"] = size(sa.viewport().size())
    d["margins"] = {"verticalFrame": list(dlg.findChild(QtWidgets.QFrame, "verticalFrame").layout().getContentsMargins()) if dlg.findChild(QtWidgets.QFrame, "verticalFrame") else None}
    return d


def drive():
    dlg = app.activeModalWidget()
    holder["polls"] += 1
    if dlg is None:
        if holder["polls"] > 80:
            holder["timer"].stop()
        return
    holder["timer"].stop()
    try:
        progress("dialog open")
        tv = [t for t in dlg.findChildren(QtWidgets.QTreeView) if t.objectName() == "groupsTreeView"][0]
        stack = dlg.findChild(QtWidgets.QStackedWidget, "groupWidgetStack")
        m = tv.model()
        res["dialog"] = dump_dialog(dlg, tv)
        dlg.grab().save(os.path.join(OUT, "freecad-prefs-dialog.png"))
        progress("tree dumped")
        # the natural size, as the real dialog opens (what showEvent computed for this screen), then tall enough for a page not to scroll
        res["dialog"]["naturalSize"] = size(dlg.size())
        by_class = {}
        for r in range(m.rowCount()):
            gi = m.index(r, 0)
            for c in range(m.rowCount(gi)):
                pi = m.index(c, 0, gi)
                tv.expand(gi)
                tv.setCurrentIndex(pi)
                tv.clicked.emit(pi)
                pump(0.4)
                cur = stack.currentWidget()
                page = cur.currentWidget() if cur is not None else None
                if page is not None:
                    by_class[cname(page)] = (gi, pi, m.data(gi), m.data(pi), page)
        for group, klass, key in PAGES:
            if ONLY and key not in ONLY:
                continue
            progress("page " + key)
            hit = by_class.get(klass)
            if not hit:
                res["errors"][key] = "page class %s is not in the dialog" % klass
                continue
            gi, pi, gname, pname, page = hit
            tv.expand(gi)
            tv.setCurrentIndex(pi)
            tv.clicked.emit(pi)
            pump(0.8)
            dlg.resize(dlg.width(), 900)
            pump(0.5)
            dlg.grab().save(os.path.join(OUT, "freecad-prefs-%s.png" % key))
            # the rectangles are read at the natural size, where a page shorter than the window is stretched as the real dialog stretches it
            info = dump_page(page)
            dlg.resize(dlg.width(), TALL)
            pump(0.9)
            dlg.grab().save(os.path.join(OUT, "freecad-prefs-%s-tall.png" % key))
            info.update(group=gname, pageTitle=pname, key=key, header=dlg.findChild(QtWidgets.QLabel, "headerLabel").text())
            try:
                info["extras"] = extras(key, page, dlg)
            except Exception:
                res["errors"]["extras-" + key] = traceback.format_exc()
            sa = dlg.findChild(QtWidgets.QScrollArea, "scrollArea")
            info["scrollContent"] = size(sa.widget().size())
            info["pageInDialog"] = rect_in(page, dlg)
            res["pages"][key] = info
            dlg.resize(dlg.width(), 900)
        # the tree again with the last group open, as the real dialog shows it after a page is picked
        res["dialog"]["treeAfter"] = dump_dialog(dlg, tv)["tree"]
    except Exception:
        res["errors"]["dialog"] = traceback.format_exc()
    finally:
        dlg.close()


holder = {"polls": 0}
mw.resize(1280, 800)
pump(1.5)
holder["timer"] = QtCore.QTimer()
holder["timer"].timeout.connect(drive)
holder["timer"].start(300)
progress("showPreferences")
Gui.showPreferences()
holder["timer"].stop()
pump(0.3)
finish()
