# SPDX-License-Identifier: LGPL-2.1-or-later
from ._dummy import QObject, Signal, _Inert, module_getattr  # noqa: F401


def Slot(*a, **k):  # noqa: N802
    return lambda f: f


def Property(*a, **k):  # noqa: N802
    return lambda f: f


def QT_TRANSLATE_NOOP(context, text):  # noqa: N802
    return text


class QCoreApplication:
    @staticmethod
    def instance():
        return None

    @staticmethod
    def translate(context, text, *a):
        return text

    @staticmethod
    def processEvents(*a):
        pass


Qt = _Inert()


# Qt resource paths (":/ui/x.ui") the runtimes resolve to folders of the vendored files (draft_runtime: Draft's .ui)
RESOURCE_DIRS: dict = {}


class QIODevice:
    ReadOnly = 1
    Text = 16


class _Bytes:
    def __init__(self, b):
        self._b = b

    def data(self):
        return self._b


class QFile:
    """QFile over the vendored resources (RESOURCE_DIRS) and plain files: open, readAll, close."""
    Text = QIODevice.Text

    def __init__(self, name):
        self._name, self._data = str(name), None

    def _path(self):
        from pathlib import Path
        if self._name.startswith(":/"):
            for prefix, d in RESOURCE_DIRS.items():
                if self._name.startswith(prefix):
                    return Path(d) / self._name[len(prefix):]
            return None
        return Path(self._name)

    def open(self, mode=None):
        p = self._path()
        if p is None or not p.is_file():
            return False
        self._data = p.read_bytes()
        return True

    def readAll(self):
        return _Bytes(self._data or b"")

    def close(self):
        self._data = None

    def exists(self):
        p = self._path()
        return p is not None and p.is_file()


class QStandardPaths:
    """Draft's params look for a default ShapeString font in the system's font folders: none here."""
    FontsLocation = 1

    @staticmethod
    def standardLocations(kind):
        return []


class _Finished:
    """QProcess::finished, as a connectable signal."""

    def __init__(self):
        self._slots = []

    def connect(self, fn):
        self._slots.append(fn)

    def emit(self, *a):
        for fn in list(self._slots):
            fn(*a)


class QProcessEnvironment:
    def __init__(self, env=None):
        import os
        self._env = dict(env if env is not None else os.environ)

    @staticmethod
    def systemEnvironment():
        return QProcessEnvironment()

    def insert(self, k, v):
        self._env[str(k)] = str(v)

    def remove(self, k):
        self._env.pop(k, None)

    def value(self, k, default=""):
        return self._env.get(k, default)

    def contains(self, k):
        return k in self._env


class QProcess(QObject):
    """QProcess for FEM's mesher and solver tools (femtools/objecttools.py: start, then waitForFinished and the finished
    signal): the program run with subprocess, its exit reported as QProcess does."""

    class ExitStatus:
        NormalExit = 0
        CrashExit = 1

    class ProcessState:
        NotRunning = 0
        Starting = 1
        Running = 2

    NormalExit, CrashExit = 0, 1

    def __init__(self, *a):
        self.finished = _Finished()
        self._p = None
        self._cwd = None
        self._env = None
        self._out = b""
        self._err = b""
        self._code = 0

    def setWorkingDirectory(self, d):
        self._cwd = str(d)

    def setProcessEnvironment(self, env):
        self._env = env._env if isinstance(env, QProcessEnvironment) else dict(env)

    def start(self, program, args=()):
        import subprocess
        self._p = subprocess.Popen([program, *[str(a) for a in args]], cwd=self._cwd, env=self._env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def waitForFinished(self, msecs=30000):
        if self._p is None:
            return False
        self._out, self._err = self._p.communicate(timeout=None if msecs is None or msecs < 0 else msecs / 1000)
        self._code = self._p.returncode
        status = QProcess.ExitStatus.NormalExit if self._code >= 0 else QProcess.ExitStatus.CrashExit
        self._p = None
        self.finished.emit(self._code, status)
        return True

    def state(self):
        return QProcess.ProcessState.Running if self._p is not None else QProcess.ProcessState.NotRunning

    def exitCode(self):
        return self._code

    def readAllStandardOutput(self):
        out, self._out = self._out, b""
        return _Bytes(out) if "_Bytes" in globals() else out

    def readAllStandardError(self):
        err, self._err = self._err, b""
        return _Bytes(err) if "_Bytes" in globals() else err

    def kill(self):
        if self._p is not None:
            self._p.kill()

    terminate = kill


class QDir:
    """QDir's current-directory calls (FEM's ccxtools runs ccx from the input file's folder)."""

    def __init__(self, path=""):
        self._path = str(path)

    @staticmethod
    def currentPath():
        import os
        return os.getcwd()

    @staticmethod
    def setCurrent(path):
        import os
        try:
            os.chdir(path)
            return True
        except OSError:
            return False

    def path(self):
        return self._path

    def exists(self):
        import os
        return os.path.isdir(self._path)


class QFileInfo:
    """QFileInfo's name parts: path() the folder, fileName(), baseName() before the first dot, suffix() after the last."""

    def __init__(self, path=""):
        self._p = str(path)

    def path(self):
        import os
        d = os.path.dirname(self._p)
        return d or "."

    def absolutePath(self):
        import os
        return os.path.dirname(os.path.abspath(self._p))

    def fileName(self):
        import os
        return os.path.basename(self._p)

    def baseName(self):
        return self.fileName().split(".", 1)[0]

    def completeBaseName(self):
        n = self.fileName()
        return n.rsplit(".", 1)[0] if "." in n else n

    def suffix(self):
        n = self.fileName()
        return n.rsplit(".", 1)[1] if "." in n else ""

    def exists(self):
        import os
        return os.path.exists(self._p)

    def absoluteFilePath(self):
        import os
        return os.path.abspath(self._p)


class QThread(QObject):
    @staticmethod
    def idealThreadCount():
        """QThread::idealThreadCount: the number of processor cores."""
        import os
        return os.cpu_count() or 1


class QTimer(QObject):
    @staticmethod
    def singleShot(ms, fn):
        pass


def __getattr__(name):
    return module_getattr(name)
