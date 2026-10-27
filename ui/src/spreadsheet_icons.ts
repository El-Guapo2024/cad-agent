// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6): the Spreadsheet workbench's icons, copied
// unmodified into public/freecad-icons/spreadsheet from src/Mod/Spreadsheet/Gui/Resources/icons; their licences are in
// public/freecad-icons/README.md and ui/NOTICE. The icon names spreadsheet.tsx draws, merged into icons.tsx's FILES:
// 'ss-' and the file's name.
const NAMES = ['Spreadsheet', 'SpreadsheetAlias', 'SpreadsheetAlignBottom', 'SpreadsheetAlignCenter', 'SpreadsheetAlignLeft', 'SpreadsheetAlignRight',
  'SpreadsheetAlignTop', 'SpreadsheetAlignVCenter', 'SpreadsheetController', 'SpreadsheetExport', 'SpreadsheetImport', 'SpreadsheetMergeCells',
  'SpreadsheetSplitCell', 'SpreadsheetStyleBold', 'SpreadsheetStyleItalic', 'SpreadsheetStyleUnderline', 'SpreadsheetWorkbench', 'preferences-spreadsheet'] as const
export const SPREADSHEET_FILES = Object.fromEntries(NAMES.map((n) => [`ss-${n}`, `spreadsheet/${n}`])) as { [K in (typeof NAMES)[number] as `ss-${K}`]: string }
