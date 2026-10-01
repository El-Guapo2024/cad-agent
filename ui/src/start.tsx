// FreeCAD's Start page (src/Mod/Start/Gui at main 3160daf1e2b6: StartView.cpp, NewFileButton.cpp,
// FileCardDelegate.cpp, FirstStartWidget.cpp), as a tab beside the 3D view. Recent Files are the
// projects this browser opened last, each with its newest render as the thumbnail.
import { useState, type FC } from 'react'
import type { IDockviewPanelProps } from 'dockview-react'
import { getDock, openProject, openTask, recentFiles } from './actions'
import { saved, setState, useStore } from './store'
import { Icon } from './icons'
import { QComboBox } from './combo'
import { SCHEMAS } from './quantity'
import { setUnits } from './commands'
import type { Project } from './api'

/** QLocale::formattedDataSize(bytes, 1, DataSizeSIFormat), what the file cards show. */
export function dataSize(n: number): string {
  if (n < 1000) return `${n} bytes`
  const units = ['kB', 'MB', 'GB', 'TB']
  let v = n / 1000, i = 0
  while (v >= 1000 && i < units.length - 1) { v /= 1000; i++ }
  return `${v.toFixed(1)} ${units[i]}`
}

/** NewFileButton: a 48px icon, a bold heading and a 180px description, in a push button. */
function NewFileButton({ icon, heading, text, onClick, disabled }: { icon: string; heading: string; text: string; onClick(): void; disabled?: boolean }) {
  return (
    <button className="qbtn start-newbtn" onClick={onClick} disabled={disabled} title={disabled ? `n/a: no ${heading} workbench here` : undefined}>
      <img src={`./freecad-icons/${icon}.svg`} width={48} height={48} alt="" draggable={false} />
      <span><b>{heading}</b><span className="start-desc">{text}</span></span>
    </button>
  )
}

/** FileCardDelegate: the 128px thumbnail, the (elided) name and the size, on a button face. */
function FileCard({ p }: { p: Project }) {
  return (
    <button className="qbtn start-card" title={p.root + '/' + p.slug} onClick={() => { openProject(p.slug); getDock()?.getPanel('view3d')?.api.setActive() }}>
      <span className="start-thumb">{p.thumb ? <img src={`/api/file?slug=${encodeURIComponent(p.slug)}&path=${encodeURIComponent(p.thumb)}`} alt="" draggable={false} /> : <Icon name="new" size={64} />}</span>
      <span className="start-name">{p.slug}</span>
      <span>{typeof p.size === 'number' ? dataSize(p.size) : ''}</span>
    </button>
  )
}

/** FirstStartWidget: language, unit system and theme, then Done. */
function FirstStart({ onDone }: { onDone(): void }) {
  const units = useStore((s) => s.units)
  return (
    <div className="start-first">
      <h1>Welcome to cad-agent</h1>
      <p>Set your basic configuration options below. These options (and many more) can be changed later in the preferences.</p>
      <div className="start-first-row">
        <label><b>Language</b><QComboBox value="en" onChange={() => {}} disabled><option value="en">English</option></QComboBox></label>
        <label><b>Unit System</b><QComboBox value={String(units.schema)} onChange={(e) => setUnits({ schema: Number(e.target.value) })}>
          {SCHEMAS.map((s) => <option key={s.num} value={s.num}>{s.description}</option>)}</QComboBox></label>
      </div>
      <h2>Theme</h2>
      <div className="start-theme"><span className="start-theme-card sel">FreeCAD Light</span></div>
      <button className="qbtn default" onClick={onDone}>Done</button>
    </div>
  )
}

export const StartPanel: FC<IDockviewPanelProps> = () => {
  const projects = useStore((s) => s.projects)
  const [first, setFirst] = useState(() => saved.get('start.firstStart', true))
  const [hide, setHide] = useState(() => !saved.get('start.showOnStartup', true))
  const recent = recentFiles().map((slug) => projects.find((p) => p.slug === slug)).filter((p): p is Project => !!p)
  const newDoc = (wb?: 'design' | 'assembly') => { if (wb) setState({ workbench: wb }); openTask('newDocument', '') }
  return (
    <div className="start">
      <div className="start-scroll">
        {first ? <FirstStart onDone={() => { saved.set('start.firstStart', false); setFirst(false) }} /> : <>
          <h1>New File</h1>
          <div className="start-new" id="CreateNewRow">
            <NewFileButton icon="PartDesignWorkbench" heading="Parametric Body" text="Creates a body with the Part Design workbench" onClick={() => newDoc('design')} />
            <NewFileButton icon="AssemblyWorkbench" heading="Assembly" text="Creates an assembly project" onClick={() => newDoc('assembly')} />
            <NewFileButton icon="DraftWorkbench" heading="2D Draft" text="Creates a 2D Draft document" onClick={() => {}} disabled />
            <NewFileButton icon="BIMWorkbench" heading="BIM/Architecture" text="Creates an architectural project" onClick={() => {}} disabled />
            <NewFileButton icon="document-new" heading="Empty File" text="Creates a new empty FreeCAD file" onClick={() => newDoc()} />
            <NewFileButton icon="document-open" heading="Open File" text="Opens an existing CAD file or 3D model" onClick={() => openTask('openDocument', '')} />
          </div>
          <h1>Recent Files</h1>
          <div className="start-files">{recent.map((p) => <FileCard key={p.slug} p={p} />)}</div>
        </>}
      </div>
      <div className="start-footer">
        <button className="qbtn" disabled={first} onClick={() => { saved.set('start.firstStart', true); setFirst(true) }}>
          <img src="./freecad-icons/preferences-general.svg" width={16} height={16} alt="" /> Open First Start Setup</button>
        <label className="qcheck-row"><input type="checkbox" checked={hide} onChange={(e) => { setHide(e.target.checked); saved.set('start.showOnStartup', !e.target.checked) }} />
          Do not show this Start page again (start with blank screen)</label>
      </div>
    </div>
  )
}

/** Start_Start: show the Start page (a new tab before the document views if it was closed). */
export function startPage() {
  const dock = getDock()
  if (!dock) return
  const p = dock.getPanel('start')
  if (p) return p.api.setActive()
  dock.addPanel({ id: 'start', component: 'start', title: 'Start', position: { referencePanel: 'view3d', direction: 'within', index: 0 } })
}
