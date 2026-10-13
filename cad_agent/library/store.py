"""The store: your own folder of vendor files, each kept under the hash of its bytes.

A vendor STEP never goes in the repo (it is not ours to publish, and a public repo is the wrong place for a
vendor's file), so the library keeps the files a user collects in a folder of theirs: $CAD_LIBRARY, else
~/.cad-agent/library. It can be a private repository, and the team shares one that way. What is in it:

    <sha256>.step     a file, named for the hash of its bytes
    library.json      the user's own entries (catalog.py) and, for each file, how it came to be there

A file is named for what it is, so there is one copy of it however many entries and projects use it, and a file
that is not what its name says (a disk error, an edit) can be told from one that is. Nothing here is ever
replaced: `put` and `download` refuse a file whose hash is not the one expected and write nothing, and a store
file that no longer hashes to its name is an error that stops anything copying from it. A project copies in what
it uses (use.py) and reads only its own tree after that, so a store that is gone, or changed, cannot change a
verdict about a design that was verified.

Nothing here imports the CAD kernel, and nothing reaches the network when it is imported: a download goes
through `OPEN`, which a test replaces. It verifies the server with the Python's own root certificates, and with
certifi's or the system's when the Python has none (tls_context says why).
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import shutil
import ssl
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from .. import bought
from ..state import write_atomic
from .catalog import FORMAT, STORE_FILE, IntegrityError, LibraryError, Unreachable, parse_entry

TIMEOUT_S = 60
SYSTEM_ROOTS = ("/etc/ssl/cert.pem",)      # macOS's bundle, the one curl uses
MAX_BYTES = 256 * 1024 * 1024              # a STEP larger than this is not one a catalog pins
CHUNK = 1 << 20
STORE_NAME = re.compile(r"^[0-9a-f]{64}\.step$")


def root_file() -> str | None:
    """A file of root certificates to verify a download with when this Python has none of its own, else None.

    python.org's macOS builds look for roots in a folder that is empty until their user runs Install Certificates.command,
    and a plugin's venv is made from whatever Python the machine has: every `lib fetch` there would fail with
    CERTIFICATE_VERIFY_FAILED, which reads as a network that did not answer. certifi's bundle comes first (requests
    brings it, with build123d), then the system's."""
    paths = ssl.get_default_verify_paths()
    if paths.cafile or paths.capath:           # None when the file or folder the Python looks in is not there
        return None
    try:
        import certifi
        found = [certifi.where(), *SYSTEM_ROOTS]
    except ImportError:
        found = list(SYSTEM_ROOTS)
    return next((p for p in found if os.path.isfile(p)), None)


def tls_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=root_file())


def OPEN(request, timeout=None):
    """urlopen with `tls_context`: replaced by tests, as fetch is the only thing in the library that uses the network."""
    return urllib.request.urlopen(request, timeout=timeout, context=tls_context())


def store_dir() -> Path:
    return bought.library_dir()


def path_of(sha: str, store: Path | None = None) -> Path:
    return (store or store_dir()) / f"{sha}.step"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def looks_like_step(path: Path) -> bool:
    """Whether a file begins the way an ISO 10303-21 file does: a clear file to refuse a drawing or a page saved by mistake."""
    with Path(path).open("rb") as f:
        return f.read(256).lstrip().startswith(b"ISO-10303-21;")


def files(store: Path | None = None) -> list[Path]:
    d = store or store_dir()
    return sorted(p for p in d.iterdir() if STORE_NAME.match(p.name)) if d.is_dir() else []


def _claim(sha: str, store: Path) -> Path:
    """The path a file of this hash goes to, or the store file that is already there, after checking that it is whole."""
    dest = path_of(sha, store)
    if dest.exists() and sha256_of(dest) != sha:
        raise IntegrityError(f"{dest} no longer hashes to its own name: it is damaged. Delete it and put the file in again")
    return dest


def put(src: Path, expect: str | None = None, store: Path | None = None) -> tuple[str, Path, bool]:
    """Copy a file into the store under its hash: (hash, where it is, whether it was new).

    A file that does not hash to `expect` is refused and nothing is written. One that is already there is left alone.
    """
    store = store or store_dir()
    sha = sha256_of(src)
    if expect and sha != expect:
        raise IntegrityError(f"{src} hashes to {sha}, not the {expect} the catalog pins for it: it is not the file "
                             "that entry stands for (a different revision, or the wrong download). Nothing was stored")
    dest = _claim(sha, store)
    if dest.exists():
        return sha, dest, False
    store.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    shutil.copyfile(src, tmp)
    os.replace(tmp, dest)
    return sha, dest, True


def download(url: str, expect: str, store: Path | None = None) -> tuple[str, Path, bool]:
    """Download `url` into the store, checking it against `expect` as it arrives: (hash, where it is, whether it was new).

    The bytes go to a temporary file beside the store's, so the store never holds half a file, and they are
    renamed into place only when they hash to what the catalog pins. A mismatch writes nothing (IntegrityError),
    and a network that did not answer is Unreachable: the caller tells those apart, since the first is a
    different file than the catalog says and the second only a download that did not happen.
    """
    store = store or store_dir()
    dest = _claim(expect, store)
    if dest.exists():
        return expect, dest, False
    store.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "cad-agent-library"})
    h, total = hashlib.sha256(), 0
    fd, tmp = tempfile.mkstemp(dir=store, prefix=".download-", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as out, OPEN(request, timeout=TIMEOUT_S) as resp:
            for chunk in iter(lambda: resp.read(CHUNK), b""):
                total += len(chunk)
                if total > MAX_BYTES:
                    raise IntegrityError(f"{url} is larger than {MAX_BYTES >> 20} MB, which no STEP the catalog pins is")
                h.update(chunk)
                out.write(chunk)
        sha = h.hexdigest()
        if sha != expect:
            raise IntegrityError(f"{url} gave a file that hashes to {sha}, not the {expect} the catalog pins: it "
                                 "has changed, or it is not the file the entry stands for. Nothing was stored")
        os.replace(tmp, dest)
        return sha, dest, True
    except IntegrityError:
        raise
    except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError) as e:
        raise Unreachable(f"could not download {url}: {getattr(e, 'reason', None) or e}") from e
    finally:
        Path(tmp).unlink(missing_ok=True)


# ─── library.json: the user's entries, and the record of the files ───────────

def read_raw(store: Path | None = None) -> dict:
    """library.json as written, or an empty one. A file that cannot be read is an error and not an empty store, because
    the next write would otherwise replace it with a record that has forgotten everything in it."""
    path = (store or store_dir()) / STORE_FILE
    if not path.exists():
        return {"format": FORMAT, "parts": {}, "files": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not (isinstance(data, dict) and data.get("format") == FORMAT
                and isinstance(data.get("parts"), dict) and isinstance(data.get("files"), dict)):
            raise ValueError(f"it must be an object with format {FORMAT}, parts and files")
    except (OSError, ValueError) as e:
        raise IntegrityError(f"{path} cannot be read ({e}); mend it or move it aside, and nothing is lost: "
                             "the files beside it are named for their hashes") from e
    return data


def write_raw(data: dict, store: Path | None = None) -> Path:
    store = store or store_dir()
    store.mkdir(parents=True, exist_ok=True)
    path = store / STORE_FILE
    write_atomic(path, json.dumps(data, indent=1, sort_keys=True) + "\n")
    return path


def record_file(sha: str, entry: str, how: str, source: str, store: Path | None = None, url: str | None = None) -> None:
    """Note how a file came to be in the store (`fetch` or `add`), for `info` and for the sidecar `use` writes."""
    data = read_raw(store)
    row = {"entry": entry, "how": how, "source": source, "when": time.strftime("%Y-%m-%d", time.gmtime())}
    if url:
        row["url"] = url
    data["files"][sha] = row
    write_raw(data, store)


def add_entry(name: str, raw: dict, store: Path | None = None, replace: bool = False) -> None:
    """Write the user's own entry into library.json, after checking it the way the loader will."""
    entry = parse_entry(name, raw, "store")
    if entry.problems:
        raise LibraryError(f"{name} would not be a valid entry: " + "; ".join(entry.problems))
    data = read_raw(store)
    if name in data["parts"] and not replace:
        raise IntegrityError(f"{name} is already in your store with another file; `--replace` takes the new file instead")
    data["parts"][name] = raw
    write_raw(data, store)
