// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Sketcher/Gui/TaskSketcherTool.cpp: 2022 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/SketcherToolDefaultWidget.cpp, SketcherToolDefaultWidget.ui: 2022 Abdullah Tahiri
// The task panel's Tool Parameters box (TaskSketcherTool): the running tool's SketcherToolDefaultWidget, its combo
// boxes, parameters and check boxes as the tool configures them (sketchovp.ts holds the model), shown while the tool is
// on and its isWidgetVisible says so (TaskDlgEditSketch::slotToolChanged). Each control carries its name in the .ui
// (data-tool-widget), for the checks.
import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { getToolWidget, subscribeToolWidget, toolWidgetVersion } from './sketchovp'
import { sketcherIcon } from './sketchdraw'
import { QuantityBox, LENGTH, ANGLE } from './qsb'
import { cls } from './panels'
import './sketchovp.css'

const PARAM_NAMES = ['parameterOne', 'parameterTwo', 'parameterThree', 'parameterFour', 'parameterFive', 'parameterSix', 'parameterSeven', 'parameterEight', 'parameterNine', 'parameterTen']
const icon = (name: string) => (name === 'document-new' ? './freecad-icons/document-new.svg' : sketcherIcon(name))

export function ToolParametersBox() {
  useSyncExternalStore(subscribeToolWidget, toolWidgetVersion)
  const w = getToolWidget()
  const [open, setOpen] = useState(true)
  const body = useRef<HTMLDivElement>(null)
  // setParameterFocus (queued): the widget's box takes the focus and its number is selected
  const focusSeq = w?.focus.seq ?? 0
  useEffect(() => {
    if (!w || w.focus.parameter < 0) return
    const el = body.current?.querySelector<HTMLInputElement>(`[data-tool-widget="${PARAM_NAMES[w.focus.parameter]}"] input`)
    if (el) { el.focus(); el.select() }
  }, [focusSeq]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!w) return null
  return (
    <div className="tbox" data-box="tool">
      <div className="tbox-head" onClick={() => setOpen(!open)}><img src={icon(w.icon)} width={16} height={16} alt="" className="ico" /><span>{w.title}</span><span className={cls('twisty', open && 'open')}>{open ? '▴' : '▾'}</span></div>
      {open && <div className="tbox-body sk-tool" ref={body}>
        {w.comboboxes.map((c, i) => c.visible && (
          <div key={`c${i}`} className="hbox fill">
            <span>{c.label}</span>
            <select className="qcombo" data-tool-widget={`comboBox${i + 1}`} value={c.index} onChange={(e) => { c.index = Number(e.target.value); w.onCombobox(i, c.index) }}>
              {c.items.map((it, k) => <option key={k} value={k}>{it.text}</option>)}
            </select>
          </div>))}
        {w.parameters.map((p, i) => p.visible && (
          <div key={`p${i}`} className="hbox fill" data-tool-widget={PARAM_NAMES[i]}
            onKeyDown={(e) => { if (e.key === 'Tab' || e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); w.onParameterTab(i) } }}>
            <span>{p.label}</span>
            <QuantityBox value={p.value} dims={p.unit === 'Angle' ? ANGLE : LENGTH} disabled={!p.enabled} min={p.min} max={p.max} decimals={p.decimals}
              onChange={(v) => { p.value = v; p.isSet = true; w.onParameter(i, v) }} />
          </div>))}
        {w.checkboxes.map((c, i) => c.visible && (
          <label key={`b${i}`} className="tcheck" title={c.toolTip}>
            <input type="checkbox" data-tool-widget={`checkBoxTS${i + 1}`} checked={c.checked} onChange={(e) => { c.checked = e.target.checked; w.onCheckbox(i, c.checked) }} />
            {c.icon && <img src={sketcherIcon(c.icon)} width={16} height={16} alt="" className="ico" />} {c.label}
          </label>))}
        {w.noticeVisible && <div className="sk-notice">{w.notice}</div>}
      </div>}
    </div>
  )
}
