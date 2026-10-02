#!/usr/bin/env python3
"""Preferences pages, label by label: FreeCAD's .ui strings against prefdump.mjs's dump.

    node ui/scripts/prefdump.mjs http://127.0.0.1:PORT/next/ prefs-dump.json
    python3 ui/scripts/prefdiff.py prefs-dump.json [PAGE ...]

Each page's .ui at 3160daf1e2b6 (DlgSettingsAdvanced.cpp's tr() strings for Advanced, whose page
is generated) is fetched once into ~/.cad-agent/freecad/ui-3160daf1e2b6/. Per page it prints the
FreeCAD strings not in ours (MISSING) and the ones only found inside a longer string or in another
case (near). Some MISSING lines aren't gaps: items of our own combo boxes (in the page only while
open), widgets shown only in another state (Colors' gradient colours), a page's own title.
"""
import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

COMMIT = "3160daf1e2b6"
CACHE = Path.home() / ".cad-agent" / "freecad" / f"ui-{COMMIT}"
PAGES = {"General": "PreferencePages/DlgSettingsGeneral.ui", "Document": "PreferencePages/DlgSettingsDocument.ui",
         "Selection": "PreferencePages/DlgSettingsSelection.ui", "Keyboard": "Dialogs/DlgKeyboard.ui",
         "Cache": "PreferencePages/DlgSettingsCacheDirectory.ui",
         "Notification Area": "PreferencePages/DlgSettingsNotificationArea.ui",
         "Report View": "PreferencePages/DlgSettingsReportView.ui", "3D View": "PreferencePages/DlgSettings3DView.ui",
         "Light Sources": "PreferencePages/DlgSettingsLightSources.ui", "UI": "PreferencePages/DlgSettingsUI.ui",
         "Navigation": "PreferencePages/DlgSettingsNavigation.ui", "Colors": "PreferencePages/DlgSettingsViewColor.ui",
         "Advanced": "PreferencePages/DlgSettingsAdvanced.cpp",
         "Available Workbenches": "PreferencePages/DlgSettingsWorkbenches.ui", "PDF": "PreferencePages/DlgSettingsPDF.ui",
         "Macro": "PreferencePages/DlgSettingsMacro.ui", "Python General": "PreferencePages/DlgSettingsPythonConsole.ui",
         "Editor": "PreferencePages/DlgSettingsEditor.ui"}
PROPS = {"text", "title", "suffix", "prefix", "specialValueText", "placeholderText"}


def norm(s: str) -> str:
    if "<" in s:  # rich text: paragraphs and breaks are spaces, other tags nothing
        s = html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"</p>|<br\s*/?>", " ", s)))
    s = s.replace("&&", "\0").replace("&", "").replace("\0", "&").replace("…", "...")
    return re.sub(r"\s+", " ", s).strip().rstrip(":").strip()


def source(path: str) -> str:
    f = CACHE / Path(path).name
    if not f.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        url = f"https://raw.githubusercontent.com/FreeCAD/FreeCAD/{COMMIT}/src/Gui/{path}"
        f.write_bytes(urllib.request.urlopen(url, timeout=30).read())
    return f.read_text()


def fc_strings(path: str) -> list[tuple[str, str]]:
    src = source(path)
    if path.endswith(".cpp"):
        return [(norm(m), "tr") for m in re.findall(r'tr\("((?:[^"\\]|\\.)*)"\)', src)]
    out = []

    def walk(el, kind):
        for ch in el:
            k = ch.tag if ch.tag in ("item", "column") and el.tag == "widget" else kind
            if ch.tag in ("property", "attribute") and ch.get("name") in PROPS:
                s = ch.find("string")
                if s is not None and (s.text or "").strip():
                    for part in s.text.split("</p>"):  # a rich-text label: each paragraph on its own
                        out.append((norm(part), k + (":" + ch.get("name") if ch.get("name") != "text" else "")))
                continue
            walk(ch, k)
    walk(ET.fromstring(src), "widget")
    return [o for o in out if o[0]]


def main() -> int:
    ours = json.loads(Path(sys.argv[1]).read_text())
    missing_total = 0
    for page in sys.argv[2:] or list(PAGES):
        mine = [norm(t) for t in ours.get(page, [])]
        exact, low = set(mine), {m.lower() for m in mine}
        blob, squeezed = " | ".join(mine).lower(), {re.sub(r"\s", "", m) for m in mine}
        missing, near = [], []
        for s, kind in dict.fromkeys(fc_strings(PAGES[page])):
            if s in exact or re.sub(r"\s", "", s) in squeezed or s == "TextLabel":
                continue
            (near if s.lower() in low or s.lower() in blob else missing).append((s, kind))
        missing_total += len(missing)
        print(f"## {page}: {len(missing)} missing, {len(near)} near")
        for s, k in missing:
            print(f"  MISSING [{k}] {s[:110]}")
        for s, k in near:
            hit = next((m for m in mine if s.lower() in m.lower()), "")
            print(f"  near    [{k}] {s[:70]}  ~ ours: {hit[:70]}")
    return 1 if missing_total else 0


if __name__ == "__main__":
    sys.exit(main())
