// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Assembly/CommandCreateBom.py: 2023 Ondsel
//   No copyright line in the file: src/Mod/Assembly/Gui/Resources/panels/TaskAssemblyCreateBom.ui
// Assembly_CreateBom's panel (TaskAssemblyCreateBom): the three options, the columns (auto ones bold, custom ones
// renamed by a double click or F2, any one removed with Delete, dragged to reorder, Add Column's menu), Export and the
// help. OK makes the Bill of Materials (`cad sheet bom`: a sheet of the project the Assembly fills, cad_agent/
// assembly_bom.py) or edits the one double-clicked, then shows its sheet.
import { useEffect, useRef, useState } from 'react'
import { closeTask } from './actions'
import { Icon } from './icons'
import { TaskBox } from './panels'
import { report } from './store'
import { applySs, exportSheetCsv, openSheet, uniqueName, useSs } from './spreadsheet'
import type { SsBom } from './spreadsheet_model'

// CommandCreateBom.ColumnNames and TranslatedColumnNames
const COLUMN_NAMES = ['Index', 'Name', 'Description', 'File Name', 'Quantity']
const SHOWN = ['Index (auto)', 'Name (auto)', 'Description', 'File Name (auto)', 'Quantity (auto)']
const shown = (n: string) => (COLUMN_NAMES.includes(n) ? SHOWN[COLUMN_NAMES.indexOf(n)] : n)
const stored = (t: string) => (SHOWN.includes(t) ? COLUMN_NAMES[SHOWN.indexOf(t)] : t)
/** isCustomColumn: Description and the columns added are custom (editable, not bold). */
const isCustom = (t: string) => !SHOWN.includes(t) || t === 'Description'
// the preferences the checkboxes start from on a new BOM (BOMOnlyParts, BOMDetailParts, BOMDetailSubAssemblies)
const PREF = 'cad.assembly.bom'
function prefs(): Pick<SsBom, 'only_parts' | 'detail_parts' | 'detail_sub_assemblies'> {
  try {
    const p = JSON.parse(localStorage.getItem(PREF) ?? '{}')
    return { only_parts: p.only_parts ?? false, detail_parts: p.detail_parts ?? true, detail_sub_assemblies: p.detail_sub_assemblies ?? true }
  } catch { return { only_parts: false, detail_parts: true, detail_sub_assemblies: true } }
}
function savePrefs(p: Pick<SsBom, 'only_parts' | 'detail_parts' | 'detail_sub_assemblies'>) {
  try { localStorage.setItem(PREF, JSON.stringify(p)) } catch { /* the preference is a convenience */ }
}

const HELP: [string, string[]][] = [
  ['Options', ['Sub-assembly children: the children of sub-assemblies will be included in the bill of materials',
    'Parts children: the children of parts will be added to the bill of materials',
    'Only parts: adds only part containers and sub-assemblies to the bill of materials. Solids like Part Design bodies, fasteners, or Part workbench primitives are ignored.']],
  ['Columns', ['Auto columns :  (Index, Quantity, Name...) are populated automatically. Any modification you make will be overridden. These columns cannot be renamed.',
    "Custom columns : 'Description' and other custom columns you add by clicking on 'Add column' will not have their data overwritten. If a column name starts with '.' followed by a property name (e.g. '.Length'), it will be auto-populated with that property value. These columns can be renamed by double-clicking or pressing F2 (renaming a column will currently lose its data).",
    '', 'Any column (custom or not), can be deleted by pressing the Delete key']],
  ['Export', ['The exported file format can be customized in the Spreadsheet workbench preferences']],
]

export function BomTask({ edit }: { edit?: string }) {
  const sheets = useSs((s) => s.sheets)
  const bom = edit ? sheets[edit]?.bom : undefined
  const start = bom ?? { columns_names: COLUMN_NAMES, ...prefs() }
  const [cols, setCols] = useState<string[]>(() => start.columns_names.map(shown))
  const [opt, setOpt] = useState({ detail_sub_assemblies: start.detail_sub_assemblies, detail_parts: start.detail_parts, only_parts: start.only_parts })
  const [cur, setCur] = useState<number | null>(null)
  const [editing, setEditing] = useState<number | null>(null)
  const [menu, setMenu] = useState(false)
  const [help, setHelp] = useState(false)
  const [drag, setDrag] = useState<number | null>(null)
  const listRef = useRef<HTMLDivElement>(null)
  useEffect(() => { if (editing === null) listRef.current?.focus() }, [editing])

  /** addColumn: "Default", made unique (Default_1, ...), then edited at once. */
  function addCustom() {
    let name = 'Default'
    for (let k = 1; cols.includes(name); k++) name = `Default_${k}`
    setCols([...cols, name]); setCur(cols.length); setEditing(cols.length); setMenu(false)
  }
  /** showAddColumnMenu: the default columns not in the list, then "Add custom column"; none left, a custom one at once. */
  function addMenu() {
    if (SHOWN.every((n) => cols.includes(n))) { addCustom(); return }
    setMenu(!menu)
  }
  /** itemUpdated: a name used twice is refused and the old one put back. */
  function rename(i: number, text: string) {
    setEditing(null)
    if (cols.some((c, k) => k !== i && c === text)) {
      report('warn', 'Duplicate Name: This name is already used. Please choose a different name.')
      return
    }
    if (text) setCols(cols.map((c, k) => (k === i ? text : c)))
  }
  async function ok() {
    const settings = { columns_names: cols.map(stored), ...opt }
    savePrefs(opt)
    const name = edit ?? uniqueName('Bill_of_Materials')
    const ops = edit ? [{ op: 'bom', ...settings }] : [{ op: 'new', label: 'Bill of Materials', bom: settings }]
    if (await applySs(name, ops, edit ? 'Edit Bill Of Materials' : 'Create Bill Of Materials')) {
      closeTask()
      openSheet(name, false)                        // accept: bomObj.ViewObject.showSheetMdi()
    }
  }
  const check = (k: keyof typeof opt, label: string, tip: string) =>
    <label className="as-check" title={tip}><input type="checkbox" data-qf={`CheckBox_${k === 'only_parts' ? 'onlyParts' : k === 'detail_parts' ? 'detailParts' : 'detailSubAssemblies'}`}
      checked={opt[k]} onChange={(e) => setOpt({ ...opt, [k]: e.target.checked })} /> {label}</label>

  return <div className="tasks as-task" data-task="bom">
    <div className="tbuttons"><button onClick={() => void ok()}>OK</button><button onClick={() => closeTask()}>Cancel</button></div>
    <TaskBox title="Bill of Materials" icon="as-bom">
      <div className="as-grid">
        {check('detail_sub_assemblies', 'Sub-assemblies children', 'Includes children of sub-assemblies in the bill of materials')}
        {check('detail_parts', 'Parts children', 'Include child parts in the bill of materials')}
        {check('only_parts', 'Only parts', 'Adds only part containers and sub-assemblies to the bill of materials. Solids (e.g. bodies, fasteners, primitives) are excluded.')}
      </div>
      <fieldset className="as-group"><legend>Columns</legend>
        <div ref={listRef} className="as-list" data-qf="columnList" tabIndex={0}
          onKeyDown={(e) => {
            if (editing !== null || cur === null) return
            if (e.key === 'Delete') { e.preventDefault(); setCols(cols.filter((_, k) => k !== cur)); setCur(null) }
            if (e.key === 'F2' && isCustom(cols[cur])) { e.preventDefault(); setEditing(cur) }
          }}>
          {cols.map((c, i) => editing === i
            ? <input key={i} autoFocus className="qline" defaultValue={c} onBlur={(e) => rename(i, e.target.value.trim())}
              onKeyDown={(e) => { if (e.key === 'Enter') rename(i, (e.target as HTMLInputElement).value.trim()); if (e.key === 'Escape') setEditing(null) }} />
            : <div key={i} className={`as-item${cur === i ? ' sel' : ''}`} draggable data-col={stored(c)}
              style={isCustom(c) ? undefined : { fontWeight: 700 }}
              onClick={() => setCur(i)} onDoubleClick={() => { if (isCustom(c)) setEditing(i) }}
              onDragStart={() => setDrag(i)} onDragOver={(e) => e.preventDefault()}
              onDrop={() => { if (drag === null || drag === i) return; const n = [...cols]; const [m] = n.splice(drag, 1); n.splice(i, 0, m); setCols(n); setCur(i); setDrag(null) }}>{c}</div>)}
        </div>
        <div style={{ position: 'relative' }}>
          <button data-qf="btnAddColumn" onClick={addMenu}>Add Column</button>
          {menu && <div className="as-menu" role="menu">
            {SHOWN.filter((n) => !cols.includes(n)).map((n) =>
              <div key={n} role="menuitem" onClick={() => { setCols([...cols, n]); setMenu(false) }}>{`Add '${n}' column`}</div>)}
            <div role="menuitem" onClick={addCustom}>Add custom column</div>
          </div>}
        </div>
      </fieldset>
      <div className="as-row">
        <button data-qf="btnExport" disabled={!edit} title={edit ? undefined : 'export after OK: the BOM is made on OK here'}
          onClick={() => edit && exportSheetCsv(edit)}>Export</button>
        <button data-qf="helpButton" className="as-help-btn" title="Help" onClick={() => setHelp(!help)}><Icon name="help" size={16} /></button>
      </div>
      {help && <div className="as-help">{HELP.map(([t, lines]) => <div key={t}><b>{t}</b>{lines.map((l, k) => <p key={k}>{l ? ` - ${l}` : ''}</p>)}</div>)}</div>}
    </TaskBox>
  </div>
}
