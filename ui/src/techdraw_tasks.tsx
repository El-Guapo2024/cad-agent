// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/TechDraw/Gui/TaskProjGroup.cpp: 2014 Joe Dowsett; 2014 Luke Parry
//   src/Mod/TechDraw/Gui/TaskSectionView.cpp: 2016 WandererFan
//   src/Mod/TechDraw/Gui/TaskDimension.cpp: 2021 Uwe Stöhr
//   src/Mod/TechDraw/Gui/TaskBalloon.cpp: 2016 WandererFan; 2019 Franck Jullien
//   No copyright line in the file: src/Mod/TechDraw/Gui/TaskProjGroup.ui, src/Mod/TechDraw/Gui/TaskSectionView.ui,
//       src/Mod/TechDraw/Gui/TaskDimension.ui, src/Mod/TechDraw/Gui/TaskBalloon.ui
// TechDraw's task panels, drawn from their Qt Designer files (uiforms-techdraw.ts) and filled as their code fills them:
// TaskProjGroup ("New View" / "Projection Group": scale, the primary direction's rotate buttons, the projections'
// check boxes, projection type, auto distribute and spacing), TaskSectionView (base view, symbol, scale, the four
// arrows, the section plane's origin), TaskDimension (format, tolerances, the override angles) and TaskBalloon. What
// a panel changes is previewed on the page (a dry run of the ops) and written as one undo step on OK, named as FreeCAD's
// transaction; Cancel of a new view or group takes the command's own step back (TaskProjGroup::reject in create mode
// removes the objects).
import { useEffect, useMemo, useState } from 'react'
import { closeTask, doUndo } from './actions'
import { QtForm, type Bindings } from './qtform'
import { TECHDRAW_FORMS } from './uiforms-techdraw'
import { TaskBox } from './panels'
import { applyTd, clearPreview, objOf, tdState, useTd, type TdObj } from './techdraw'
import type { IconName } from './icons'
import { AnnotTask } from './techdraw_annot'
import { MoreTask, MORE_KINDS } from './techdraw_more'
import { LineAttrsTask } from './techdraw_ext'

const icon = (file: string, size: number) => <img src={`./freecad-icons/techdraw/${file}.svg`} width={size} height={size} alt="" />

function Buttons({ ok, cancel, okOff }: { ok(): void; cancel(): void; okOff?: boolean }) {
  return (
    <div className="tbuttons">
      <button className="qbtn default" disabled={okOff} onClick={ok}>OK</button>
      <button className="qbtn" onClick={cancel}>Cancel</button>
    </div>)
}

export function TechDrawTask({ page, other }: { page: string; other: string }) {
  const [kind, name, mode] = other.split(':')
  const create = mode === 'create'
  if (MORE_KINDS.includes(kind)) return <MoreTask page={page} other={other} />
  if (kind === 'lineattrs') return <LineAttrsTask />
  if (['cosvertex', 'cosline', 'coscircle', 'centerline', 'linedecor', 'hatch', 'geomhatch'].includes(kind)) return <AnnotTask page={page} other={other} />
  useEffect(() => () => clearPreview(page), [page])
  if (kind === 'projgroup') return <ProjGroupTask key={other} page={page} name={name} create={create} />
  if (kind === 'section') return <SectionTask key={other} page={page} name={name} create={create} />
  if (kind === 'dimension') return <DimensionTask key={other} page={page} name={name} />
  if (kind === 'balloon') return <BalloonTask key={other} page={page} name={name} />
  return null
}

/** The ops a panel has collected, previewed as they change (a dry run on the server). */
function usePending(page: string) {
  const [ops, setOps] = useState<Record<string, unknown>[]>([])
  useEffect(() => { if (ops.length) void applyTd(page, ops, undefined, true); else clearPreview(page) }, [ops, page])
  const preview = useTd((s) => s.preview[page] ?? s.docs[page])
  const get = (n: string): TdObj | undefined => preview?.objects.find((o) => o.name === n)
  return { ops, add: (op: Record<string, unknown>) => setOps((x) => [...x, op]), get, preview }
}

// ── TaskProjGroup ────────────────────────────────────────────────────────────────────────────────────────────────
/** viewChkIndexToCStr: the check boxes' projections, first or third angle. */
const BOXES_FIRST = ['FrontBottomRight', 'Bottom', 'FrontBottomLeft', 'Right', 'Front', 'Left', 'Rear', 'FrontTopRight', 'Top', 'FrontTopLeft']
const BOXES_THIRD = ['FrontTopLeft', 'Top', 'FrontTopRight', 'Left', 'Front', 'Right', 'Rear', 'FrontBottomLeft', 'Bottom', 'FrontBottomRight']
/** DrawUtil::nearestFraction, as setFractionalScale shows a scale. */
function fraction(v: number): [number, number] {
  let best: [number, number] = [1, 1], err = Infinity
  for (let d = 1; d <= 999; d++) { const n = Math.round(v * d); if (n < 1) continue; const e = Math.abs(n / d - v); if (e < err - 1e-12) { err = e; best = [n, d] } if (e < 1e-9) break }
  return best
}
function ProjGroupTask({ page, name, create }: { page: string; name: string; create: boolean }) {
  const p = usePending(page)
  const [target, setTarget] = useState(name)
  const o = p.get(target) ?? objOf(page, target)
  const isGroup = o?.kind === 'DrawProjGroup'
  const pageObj = p.preview?.objects.find((x) => x.kind === 'DrawPage')
  const third = isGroup ? (o!.projection_type === 'Third angle' || (o!.projection_type === 'Default' && pageObj?.projection_type === 'Third angle')) : false
  const boxes = third ? BOXES_THIRD : BOXES_FIRST
  const have = new Set(isGroup ? (o!.views as string[]).map((n) => p.get(n)?.item_type as string) : ['Front'])
  const anchor = isGroup ? p.get(o!.anchor as string) : o
  const dir = (anchor?.direction as number[] | undefined) ?? [0, -1, 0]
  const scale = Number(o?.scale ?? 1)
  const [num, den] = fraction(scale)
  const scaleType = String(o?.scale_type ?? 'Page')
  const toggle = (t: string, on: boolean) => {
    if (!isGroup && on) {
      // turnViewToProjGroup: the group made on the first box ticked takes the next free ProjGroup name
      const taken = new Set([...Object.values(tdState().docs).flatMap((d) => d.objects.map((x) => x.name)), ...(p.preview?.objects.map((x) => x.name) ?? [])])
      let g = 'ProjGroup', i = 0
      while (taken.has(g)) g = `ProjGroup${String(++i).padStart(3, '0')}`
      p.add({ op: 'projection', group: target, type: t, on })
      setTarget(g)
      return
    }
    p.add({ op: 'projection', group: target, type: t, on })
    if (isGroup && !on && (o!.views as string[]).length === 2) setTarget(o!.anchor as string)   // turnProjGroupToView
  }
  const bind: Bindings = {
    cmbScaleType: { value: ['Page', 'Automatic', 'Custom'].indexOf(scaleType), opts: [[0, 'Page'], [1, 'Automatic'], [2, 'Custom']],
      set: (i: number) => p.add({ op: 'set', name: target, props: { scale_type: ['Page', 'Automatic', 'Custom'][i] } }) },
    sbScaleNum: { value: num, min: 1, max: 999, set: (n: number) => p.add({ op: 'set', name: target, props: { scale: n / den } }), off: scaleType !== 'Custom' },
    sbScaleDen: { value: den, min: 1, max: 999, set: (d: number) => p.add({ op: 'set', name: target, props: { scale: num / d } }), off: scaleType !== 'Custom' },
    lePrimary: { text: `[${dir.map((c) => c.toFixed(2)).join(' ')}]`, off: true, why: 'the direction is set with the rotate buttons here' },
    projection: { value: ['First angle', 'Third angle', 'Default'].indexOf(String(o?.projection_type ?? 'First angle')), hide: !isGroup,
      opts: [[0, 'First angle'], [1, 'Third angle'], [2, 'Page']], set: (i: number) => p.add({ op: 'set', name: target, props: { projection_type: ['First angle', 'Third angle', 'Default'][i] } }) },
    label_7: { hide: !isGroup }, label_10: { hide: !isGroup }, label_11: { hide: !isGroup },
    cbAutoDistribute: { hide: !isGroup, value: o?.auto_distribute !== false, set: (v: boolean) => p.add({ op: 'set', name: target, props: { auto_distribute: v } }) },
    sbXSpacing: { hide: !isGroup, value: Number(o?.spacing_x ?? 15), suffix: ' mm', max: 1e6, set: (v: number) => p.add({ op: 'set', name: target, props: { spacing_x: v } }), off: o?.auto_distribute === false },
    sbYSpacing: { hide: !isGroup, value: Number(o?.spacing_y ?? 15), suffix: ' mm', max: 1e6, set: (v: number) => p.add({ op: 'set', name: target, props: { spacing_y: v } }), off: o?.auto_distribute === false },
    directionGroupbox: {}, secondaryProjGroupbox: {}, label: {}, label_4: {},
  }
  const rot: [string, string, string][] = [['butTopRotate', 'Up', 'arrow-up'], ['butDownRotate', 'Down', 'arrow-down'], ['butLeftRotate', 'Left', 'arrow-left'],
    ['butRightRotate', 'Right', 'arrow-right'], ['butCWRotate', 'CW', 'arrow-cw'], ['butCCWRotate', 'CCW', 'arrow-ccw'], ['butFront', 'Front', 'TechDraw_ProjFront']]
  for (const [w, motion, file] of rot) bind[w] = { node: icon(file, 24), click: () => p.add({ op: 'rotate', name: target, motion }) }
  bind.butCam = { node: icon('TechDraw_CameraOrientation', 24), off: true, why: 'the camera\'s direction is given when the view is made' }
  boxes.forEach((t, i) => {
    bind[`chkView${i}`] = { value: have.has(t), tip: t, set: (v: boolean) => toggle(t, v), off: t === 'Front' }
  })
  const ok = async () => {
    if (p.ops.length) await applyTd(page, p.ops, create ? (isGroup || target !== name ? 'Create projection group' : 'Create view') : (isGroup ? 'Edit Projection Group' : 'Edit Part View'))
    clearPreview(page)
    closeTask()
  }
  const cancel = () => { clearPreview(page); closeTask(); if (create) void doUndo() }
  const title = isGroup ? 'Projection Group' : 'New View'
  return (
    <div className="tasks">
      <Buttons ok={() => void ok()} cancel={cancel} />
      <TaskBox title={title} icon={'td-TechDraw_ProjectionGroup' as IconName}><QtForm form={TECHDRAW_FORMS.projgroup} bind={bind} /></TaskBox>
    </div>)
}

// ── TaskSectionView ──────────────────────────────────────────────────────────────────────────────────────────────
/** TaskSectionView::apply in create mode: createSectionView ("Create Section View": the origin to six decimals) and then, the
 *  section being valid, updateSectionView ("Edit Section View": the origin to three, the symbol, the scale), two undo steps; the
 *  second is made even when it sets what is there already (a FreeCAD transaction that sets a property is not empty). */
async function createSection(page: string, base: string, op: Record<string, unknown>) {
  const before = new Set(tdState().docs[page]?.objects.map((o) => o.name))
  const round = (v: unknown, n: number) => (v as number[]).map((x) => Number(x.toFixed(n)))
  const made = await applyTd(page, [{ ...op, origin: round(op.origin, 6) }], 'Create Section View')
  const sec = made?.objects.find((o) => o.kind === 'DrawViewSection' && !before.has(o.name))
  if (!sec) return
  const scale = Number(sec.scale)
  await applyTd(page, [{ op: 'section_edit', name: sec.name, origin: round(op.origin, 3), symbol: op.symbol, scale: Number(scale.toFixed(7)) }],
    'Edit Section View', false, false, true)
  void base
}
function SectionTask({ page, name, create }: { page: string; name: string; create: boolean }) {
  const doc = useTd((s) => s.docs[page])
  const section = !create ? objOf(page, name) : undefined
  const base = create ? objOf(page, name) : objOf(page, String(section?.base_view))
  const centroid = (doc?.result?.views[base?.name ?? '']?.['centroid' as never] as unknown as number[] | undefined) ?? [0, 0, 0]
  const [symbol, setSymbol] = useState(String(section?.section_symbol ?? ''))
  const [origin, setOrigin] = useState<number[]>((section?.section_origin as number[] | undefined) ?? centroid)
  const [arrow, setArrow] = useState<string | null>(null)
  const scaleType = String(section?.scale_type ?? base?.scale_type ?? 'Page')
  const [scale, setScale] = useState(Number(section?.scale ?? base?.scale ?? 1))
  const ops = useMemo(() => {
    if (create) return arrow ? [{ op: 'section', base_view: name, direction: arrow, origin, symbol }] : []
    const op: Record<string, unknown> = { op: 'section_edit', name, origin, symbol, scale }
    if (arrow) op.direction = arrow
    return [op]
  }, [arrow, origin, symbol, scale, create, name])
  useEffect(() => { if (ops.length) void applyTd(page, ops, undefined, true) }, [ops, page])
  const bind: Bindings = {
    leBaseView: { value: base?.name ?? '' }, leSymbol: { value: symbol, set: (v: string) => setSymbol(v) },
    cmbScaleType: { value: ['Page', 'Automatic', 'Custom'].indexOf(scaleType), opts: [[0, 'Page'], [1, 'Automatic'], [2, 'Custom']], off: true, why: 'the base view\'s' },
    sbScale: { value: scale, set: (v: number) => setScale(v), off: scaleType !== 'Custom', max: 1000, dec: 2 },
    sbOrgX: { value: origin[0], suffix: ' mm', min: -1e6, max: 1e6, set: (v: number) => setOrigin([v, origin[1], origin[2]]) },
    sbOrgY: { value: origin[1], suffix: ' mm', min: -1e6, max: 1e6, set: (v: number) => setOrigin([origin[0], v, origin[2]]) },
    sbOrgZ: { value: origin[2], suffix: ' mm', min: -1e6, max: 1e6, set: (v: number) => setOrigin([origin[0], origin[1], v]) },
    pbUpdateNow: { off: !arrow && create, click: () => { if (ops.length) void applyTd(page, ops, undefined, true) } },
    cbLiveUpdate: { value: true, off: true, why: 'the page shows every change at once' },
    lPendingUpdates: { text: create && !arrow ? 'No direction set' : '' },
    gbOrientation: {}, gbPlane: {}, gbUpdate: {}, label_7: {}, label_2: {}, label_3: {}, label: {}, label_10: {}, label_11: {}, label_12: {},
  }
  for (const [w, dir, file] of [['pbUp', 'Up', 'section-up'], ['pbDown', 'Down', 'section-down'], ['pbLeft', 'Left', 'section-left'], ['pbRight', 'Right', 'section-right']] as const)
    bind[w] = { node: icon(file, 48), click: () => setArrow(dir), cls: arrow === dir ? 'on' : undefined }
  const ok = async () => {
    if (create && !arrow) { closeTask(); return }
    clearPreview(page)
    closeTask()
    if (!create) await applyTd(page, ops, 'Edit Section View')
    else await createSection(page, name, ops[0])
  }
  return (
    <div className="tasks">
      <Buttons ok={() => void ok()} cancel={() => { clearPreview(page); closeTask() }} />
      <TaskBox title={create ? 'Create Section View' : 'Edit Section View'} icon={'td-TechDraw_SectionView' as IconName}>
        <QtForm form={TECHDRAW_FORMS.section} bind={bind} /></TaskBox>
    </div>)
}

// ── TaskDimension ────────────────────────────────────────────────────────────────────────────────────────────────
const SPEC = /%\.([0-9]+)([fFrRgGwWeE])/
function DimensionTask({ page, name }: { page: string; name: string }) {
  const d = objOf(page, name)
  const [v, setV] = useState<Record<string, unknown>>(() => ({ ...(d ?? {}) }))
  const set = (k: string, x: unknown) => setV((o) => {
    const n = { ...o, [k]: x }
    if (k === 'equal_tolerance' && x) { if (Number(n.over_tolerance) < 0) n.over_tolerance = 0; n.under_tolerance = -Number(n.over_tolerance); n.format_spec_under_tolerance = n.format_spec_over_tolerance }
    if (k === 'over_tolerance' && n.equal_tolerance) n.under_tolerance = -Number(x)
    if (k === 'theoretical_exact' && x) { n.over_tolerance = 0; n.under_tolerance = 0; n.arbitrary_tolerances = false }
    return n
  })
  const keys = ['format_spec', 'arbitrary', 'theoretical_exact', 'equal_tolerance', 'over_tolerance', 'under_tolerance', 'format_spec_over_tolerance',
    'format_spec_under_tolerance', 'arbitrary_tolerances', 'angle_override', 'line_angle', 'extension_angle']
  const changed = d ? Object.fromEntries(keys.filter((k) => JSON.stringify(v[k]) !== JSON.stringify(d[k])).map((k) => [k, v[k]])) : {}
  useEffect(() => { if (Object.keys(changed).length) void applyTd(page, [{ op: 'set', name, props: changed }], undefined, true); else clearPreview(page) }, [JSON.stringify(changed)]) // eslint-disable-line react-hooks/exhaustive-deps
  const spec = String(v.format_spec ?? '')
  const m = SPEC.exec(spec)
  const decimals = m ? Number(m[1]) : 2
  const angular = d?.dim_type === 'Angle' || d?.dim_type === 'Angle3Pt'
  const unit = angular ? ' °' : ' mm'
  const exact = v.theoretical_exact === true, equal = v.equal_tolerance === true
  const bind: Bindings = {
    leFormatSpecifier: { value: spec, set: (x: string) => set('format_spec', x) },
    cbArbitrary: { value: v.arbitrary === true, set: (x: boolean) => set('arbitrary', x) },
    // onNumDecChanged: the spec's precision rewritten, its prefix, conversion and suffix kept
    sbNumDecimals: { value: decimals, min: 0, max: 99, set: (n: number) => set('format_spec', m ? spec.replace(SPEC, `%.${n}${m[2]}`) : `${spec}%.${n}w`) },
    cbReference: { value: /\(%\.[0-9]+[fFrRgGwWeE]\)/.test(spec), set: (x: boolean) => set('format_spec', x ? `(${spec})` : spec.replace(/^\((.*)\)$/, '$1')) },
    cbTheoreticallyExact: { value: exact, set: (x: boolean) => set('theoretical_exact', x) },
    cbEqualTolerance: { value: equal, set: (x: boolean) => set('equal_tolerance', x), off: exact },
    qsbOvertolerance: { value: Number(v.over_tolerance ?? 0), suffix: unit, min: equal ? 0 : -1e6, max: 1e6, set: (x: number) => set('over_tolerance', x), off: exact },
    qsbUndertolerance: { value: Number(v.under_tolerance ?? 0), suffix: unit, min: -1e6, max: 1e6, set: (x: number) => set('under_tolerance', x), off: exact || equal },
    leFormatSpecifierOverTolerance: { value: String(v.format_spec_over_tolerance ?? ''), off: exact, set: (x: string) => { set('format_spec_over_tolerance', x); if (equal && !v.arbitrary_tolerances) set('format_spec_under_tolerance', x) } },
    leFormatSpecifierUnderTolerance: { value: String(v.format_spec_under_tolerance ?? ''), off: exact || equal, set: (x: string) => set('format_spec_under_tolerance', x) },
    cbArbitraryTolerances: { value: v.arbitrary_tolerances === true, off: exact, set: (x: boolean) => set('arbitrary_tolerances', x) },
    cbArrowheads: { off: true, why: 'the page draws ISO oriented arrows only' }, dimensionColor: { off: true, why: 'dimensions are drawn black' },
    qsbFontSize: { value: 5, suffix: ' mm', off: true, why: 'Preferences > TechDraw\'s 5 mm' },
    comboDrawingStyle: { value: 0, opts: [[0, 'ISO Oriented']], off: true, why: 'the page draws ISO oriented dimensions' },
    gbLines: { value: v.angle_override === true, set: (x: boolean) => set('angle_override', x) },
    dsbDimAngle: { value: Number(v.line_angle ?? 0), min: -360, max: 360, set: (x: number) => set('line_angle', x) },
    dsbExtAngle: { value: Number(v.extension_angle ?? 0), min: -360, max: 360, set: (x: number) => set('extension_angle', x) },
    pbDimUseDefault: { click: () => set('line_angle', 0) }, pbExtUseDefault: { click: () => set('extension_angle', 0) },
    pbDimUseSelection: { off: true, why: 'pick the angle from a selection: not ported' }, pbExtUseSelection: { off: true, why: 'pick the angle from a selection: not ported' },
    gbTolerancing: {}, gbFormatting: {}, gbDisplayStyle: {},
  }
  const ok = async () => {
    if (Object.keys(changed).length) await applyTd(page, [{ op: 'set', name, props: changed }], 'TaskDimension')
    clearPreview(page)
    closeTask()
  }
  return (
    <div className="tasks">
      <Buttons ok={() => void ok()} cancel={() => { clearPreview(page); closeTask() }} />
      <TaskBox title="Dimension" icon={'td-TechDraw_Dimension' as IconName}><QtForm form={TECHDRAW_FORMS.dimension} bind={bind} /></TaskBox>
    </div>)
}

// ── TaskBalloon ──────────────────────────────────────────────────────────────────────────────────────────────────
const SHAPES = ['Circular', 'None', 'Triangle', 'Inspection', 'Hexagon', 'Square', 'Rectangle', 'Line']
const ENDS = ['Filled arrow', 'Open arrow', 'Tick', 'Dot', 'Open circle', 'Fork', 'Filled triangle', 'None']
function BalloonTask({ page, name }: { page: string; name: string }) {
  const b = objOf(page, name)
  const [v, setV] = useState<Record<string, unknown>>(() => ({ ...(b ?? {}) }))
  const keys = ['text', 'bubble_shape', 'shape_scale', 'end_type', 'end_type_scale', 'kink_length']
  const changed = b ? Object.fromEntries(keys.filter((k) => JSON.stringify(v[k]) !== JSON.stringify(b[k])).map((k) => [k, v[k]])) : {}
  useEffect(() => { if (Object.keys(changed).length) void applyTd(page, [{ op: 'set', name, props: changed }], undefined, true); else clearPreview(page) }, [JSON.stringify(changed)]) // eslint-disable-line react-hooks/exhaustive-deps
  const set = (k: string) => (x: unknown) => setV((o) => ({ ...o, [k]: x }))
  const bind: Bindings = {
    leText: { value: String(v.text ?? ''), set: set('text') }, textColor: { off: true, why: 'balloons are drawn black' },
    qsbFontSize: { value: 5, suffix: ' mm', off: true, why: 'Preferences > TechDraw\'s 5 mm' },
    comboBubbleShape: { value: SHAPES.indexOf(String(v.bubble_shape)), opts: SHAPES.map((x, i) => [i, x] as const), set: (i: number) => set('bubble_shape')(SHAPES[i]) },
    qsbShapeScale: { value: Number(v.shape_scale ?? 1), min: 0.1, max: 100, set: set('shape_scale') },
    comboEndSymbol: { value: ENDS.indexOf(String(v.end_type)), opts: ENDS.map((x, i) => [i, x] as const), set: (i: number) => set('end_type')(ENDS[i]) },
    qsbSymbolScale: { value: Number(v.end_type_scale ?? 1), min: 0.1, max: 100, set: set('end_type_scale') },
    qsbLineWidth: { value: 0.35, suffix: ' mm', off: true, why: 'the line group\'s thin line' },
    qsbKinkLength: { value: Number(v.kink_length ?? 5), suffix: ' mm', max: 1000, set: set('kink_length') },
    gbAnnotation: {}, gbBubble: {}, gbLeader: {},
  }
  const ok = async () => {
    if (Object.keys(changed).length) await applyTd(page, [{ op: 'set', name, props: changed }], 'Edit Balloon')
    clearPreview(page)
    closeTask()
  }
  return (
    <div className="tasks">
      <Buttons ok={() => void ok()} cancel={() => { clearPreview(page); closeTask() }} />
      <TaskBox title="Balloon" icon={'td-TechDraw_Balloon' as IconName}><QtForm form={TECHDRAW_FORMS.balloon} bind={bind} /></TaskBox>
    </div>)
}
