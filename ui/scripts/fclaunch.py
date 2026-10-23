"""Start FreeCAD's GUI with a script, for fcgui.py and fcshots.py: all its user files in a temporary folder.

    from fclaunch import run_freecad
    r = run_freecad(Path("dump.py"), Path("out"), platform="cocoa")

FREECAD_APP overrides where FreeCAD.app is (default ~/.cad-agent/freecad/FreeCAD.app). FreeCAD's user
files (user.cfg, its data and cache) go to a temporary folder, never to ~/Library or ~/.cad-agent. The
script runs inside FreeCAD (it sees FCGUI_OUT, the output folder) and ends the process itself with
os._exit(0); a script that hangs is killed after `timeout` seconds.

Two Qt platforms:

* "offscreen": no window, no OpenGL. The chrome (menus, toolbars, docks, dialogs) is real, the 3D view
  stays blank (a QOpenGLWidget cannot get a context), and the font is Qt's fallback ("Sans Serif"), not the
  Mac's. What fcgui.py has always used, so its dump keeps the same numbers.
* "cocoa" (macOS): the real platform, so OpenGL works and the 3D view, the NaviCube and the corner
  axis cross render, in the Mac's own font and with the Mac's key bindings (qplatformtheme: Close is
  Cmd+W, Redo Shift+Cmd+Z, and so on, where offscreen has the generic ones). Nothing may reach the
  desktop: a Mod's InitGui.py (written into the temporary user data folder) runs while the GUI starts,
  before the main window is shown, and gives the main window, and every window or menu that is polished later,
  Qt::WA_DontShowOnScreen. Such a widget still paints and can be grabbed (`grab()`, `grabFramebuffer()`), but
  has no native window: no Dock icon (QT_MAC_DISABLE_FOREGROUND_APPLICATION_TRANSFORM), no focus, and a menu
  popped up at the real pointer's position (QCursor::pos(), which nothing here moves) is not on screen either.
  The colour scheme is forced to Light and the user.cfg starts as FreeCAD's own "FreeCAD Light" preference
  pack: left alone, FreeCAD picks its Dark theme when macOS is in dark mode. `scale` is QT_SCALE_FACTOR:
  0.5 on a Retina screen gives devicePixelRatio 1, so a 1280 x 800 window grabs as 1280 x 800 pixels (the
  size of the Playwright shots of the page); 1.5 gives 3.

On Linux, FREECAD_APP is an unpacked AppImage (the folder holding usr/bin/freecad). "cocoa" then means the X11
platform ("xcb": run under xvfb-run, so OpenGL works and nothing reaches a real screen), with the same hiding and the
same Light pack, and `scale` is doubled (no Retina screen: devicePixelRatio 1 at QT_SCALE_FACTOR 1). Qt's style
metrics differ from the Mac's there, so widget sizes measured on Linux are Linux numbers.
"""
import os
import subprocess
import sys
from pathlib import Path

APP = Path(os.environ.get("FREECAD_APP", "~/.cad-agent/freecad/FreeCAD.app")).expanduser()
LINUX = (APP / "usr" / "bin" / "freecad").exists()     # an unpacked AppImage, not FreeCAD.app
SHARE = APP / "usr" / "share" if LINUX else APP / "Contents" / "Resources" / "share"

INITGUI = '''\
# fclaunch.py's Mod: runs while FreeCAD's GUI starts, before the main window is shown. Nothing may reach the desktop.
# (FreeCAD execs an InitGui.py with separate globals and locals: a name imported here is not visible inside a
# function defined here, so the function imports its own.)
import os
if os.environ.get("FCSHOTS_HIDE") == "1":
    import FreeCADGui as Gui
    from PySide6 import QtCore, QtWidgets

    class Hider(QtCore.QObject):
        def eventFilter(self, obj, ev):
            from PySide6 import QtCore as qc, QtWidgets as qw
            if ev.type() == qc.QEvent.Type.Polish and isinstance(obj, qw.QWidget) and obj.isWindow():
                obj.setAttribute(qc.Qt.WA_DontShowOnScreen, True)
            return False

    app = QtWidgets.QApplication.instance()
    app._fcshots_hider = Hider(app)
    app.installEventFilter(app._fcshots_hider)
    app.styleHints().setColorScheme(QtCore.Qt.ColorScheme.Light)
    Gui.getMainWindow().setAttribute(QtCore.Qt.WA_DontShowOnScreen, True)
'''


def light_pack() -> str:
    """FreeCAD's own "FreeCAD Light" preference pack: what a new user who picks the Light theme gets."""
    return (SHARE / "Gui/PreferencePacks/FreeCAD Light/FreeCAD Light.cfg").read_text()


def freecad_exe() -> Path:
    exe = APP / "usr" / "bin" / "freecad" if LINUX else APP / "Contents" / "MacOS" / "FreeCAD"
    if not exe.exists():
        sys.exit(f"fclaunch: no FreeCAD at {exe} (set FREECAD_APP)")
    return exe


def run_freecad(script: Path, out: Path, home: Path, platform: str = "offscreen", scale: float = 0.5,
                timeout: int = 300, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run `script` inside FreeCAD's GUI; the temporary user files are under `home` (an existing, empty folder)."""
    out.mkdir(parents=True, exist_ok=True)
    e = {**os.environ, "FCGUI_OUT": str(out), "QT_QPA_PLATFORM": "xcb" if LINUX and platform == "cocoa" else platform, "FREECAD_USER_HOME": str(home),
         "FREECAD_USER_DATA": str(home / "data"), "FREECAD_USER_TEMP": str(home / "tmp"), **(env or {})}
    if platform == "cocoa":
        (home / "data" / "Mod" / "fcshots").mkdir(parents=True)
        (home / "data" / "Mod" / "fcshots" / "InitGui.py").write_text(INITGUI)
        (home / "user.cfg").write_text(light_pack())
        e.update(FCSHOTS_HIDE="1", QT_MAC_DISABLE_FOREGROUND_APPLICATION_TRANSFORM="1", QT_SCALE_FACTOR=str(scale * 2 if LINUX else scale))
    p = subprocess.Popen([str(freecad_exe()), str(script)], env=e, stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        stdout, _ = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        stdout, _ = p.communicate()
        stdout += f"\nfclaunch: killed after {timeout} s"
    return subprocess.CompletedProcess(p.args, p.returncode, stdout, "")
