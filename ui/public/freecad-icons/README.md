# FreeCAD icons

These icons are copied unmodified from FreeCAD
(https://github.com/FreeCAD/FreeCAD, `src/Gui/Icons` and
`src/Mod/*/Gui/Resources/icons`). They were taken at tag `1.1.4` and are
byte-identical on `main` at 3160daf1e2b6 (2026-09-29), the version the UI follows;
the later additions were taken from that commit. They are placeholders, to be replaced with
our own set later.

The `overlay-*.svg` files (the dock overlay panel's title bar buttons) come from a third
location, `src/Gui/Stylesheets/overlay/icons/*.svg` (light-theme variants, i.e. the files
with no `_light`/`_lightgray` suffix); renamed with an `overlay-` prefix here to avoid
clashing with unrelated icons of the same short name.

Licences, as each file's metadata states:

- Most are LGPL-2.0-or-later (`FreeCAD LGPL2+`). Files with no licence in their
  metadata come under FreeCAD's licence, LGPL-2.1 (see `LICENSE`, copied from
  the FreeCAD repository).
- CC-BY-SA 2.0 (Tango Desktop Project and derivatives): `Std_ViewScreenShot.svg`,
  `help-browser.svg`, `utilities-terminal.svg`, `zoom-selection.svg`, `view-fullscreen.svg`,
  `zoom-border.svg`, `zoom-in.svg`, `zoom-out.svg`, `accessories-text-editor.svg`,
  `media-playback-start.svg`, `media-playback-stop.svg`, `applications-accessories.svg`.
- CC-BY-SA 4.0 as well as `FreeCAD LGPL2+` (both in the metadata): `Std_UserEditModeDefault.svg`,
  `Std_UserEditModeTransform.svg`, `Std_UserEditModeCutting.svg`, `Std_UserEditModeColor.svg`.
- Public domain: `process-stop.svg`, `accessories-calculator.svg` (CC0 1.0, Jakub Steiner),
  and `internet-web-browser.svg`.
- `cursor-pan.svg`, `cursor-rotate.svg`, `cursor-zoom.svg`, `MassPropertiesIcon.svg`, `media-record.svg`,
  `Std_WindowTileVer.svg`, `Std_WindowCascade.svg`, `Std_WindowNext.svg` and `Std_WindowPrev.svg`
  carry no licence metadata, so FreeCAD's LGPL-2.1 applies.

Credit: the FreeCAD project and the icon authors named in each file's metadata.

qss-*.svg: FreeCAD's stylesheet indicator and scroll-bar arrow images, src/Gui/Stylesheets/images_classic/ at 3160daf1e2b6 (LGPL-2.1-or-later).
