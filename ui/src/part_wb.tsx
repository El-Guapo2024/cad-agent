// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Part/Gui/Workbench.cpp: 2005 Werner Mayer
//   src/Mod/Part/Gui/Command.cpp: 2002 Jürgen Riegel
//   src/Mod/Part/Gui/CommandParametric.cpp: 2002 Jürgen Riegel
//   src/Mod/Part/Gui/CommandSimple.cpp: 2002 Jürgen Riegel
//   src/Mod/Part/Gui/ViewProviderBoolean.cpp: 2008 Werner Mayer
//   src/Mod/Part/Gui/ViewProviderMirror.cpp: 2010 Werner Mayer
//   src/Mod/Part/Gui/ViewProviderExtrusion.cpp: 2008 Werner Mayer
//   src/Mod/Part/Gui/ViewProviderCompound.cpp: 2013 Werner Mayer
//   src/Mod/Part/BOPTools/BOPFeatures.py: 2023 Werner Mayer
//   src/Mod/Part/BOPTools/SplitFeatures.py: 2016 Victor Titov (DeepSOIC)
//   src/Mod/Part/BOPTools/JoinFeatures.py: 2016 Victor Titov (DeepSOIC)
//   src/Mod/Part/CompoundTools/Explode.py: no copyright line (LGPL-2.1-or-later, as its SPDX line says)
//   src/Gui/Tree.cpp: 2004 Jürgen Riegel
//   src/Gui/CommandDoc.cpp: 2002 Jürgen Riegel
// The Part workbench, for part files of Part objects (cad_agent/feature_part.py: OBJECTS beside a Body's FEATURES): the
// workbench's Part menu and its Solids, Part Tools and Boolean Tools toolbars, the commands that make objects from the
// selection as FreeCAD's do (the same names, labels, undo steps, the inputs they hide), the tree of a document with each
// object's inputs under it (claimChildren) and the hidden ones greyed, the property view, Space, Delete and F2. Every edit
// is `cad feature apply` on the server (POST /api/<slug>/features/<part>), one undo step; the part rebuilds there. The task
// panels (Primitives, Tube, Extrude, Revolve, Mirror, Fillet, Chamfer, Loft, Sweep, Offset, Thickness, ...) are part_tasks.tsx's.
import { useEffect, useState, type ReactNode } from 'react'
import * as THREE from 'three'
import { api, resultText, type Body, type FeatureOp } from './api'
import { consoleLog, getState, report, setState, subscribe, useStore, type Feature, type FeatureDoc, type State } from './store'
import { editSketch, getView, loadFeatures, loadHistory, openTask } from './actions'
import { Icon, type IconName } from './icons'
import { cls, EditRow, Group, Row, Twisty, propPad } from './panels'
import { QComboBox } from './combo'
import { messageBox } from './msgbox'
import * as quantity from './quantity'
import type { Entry } from './chrome'
import { applyOps, bodyOfPart, numberOf, refOf, sketchObject, splitRef, SKETCH, type TreeCtx } from './partdesign'
import { attachedOf } from './attached'
import { PART_PROPS, type PartProp } from './part_props'

// ── the model ────────────────────────────────────────────────────────────────────────────────────────────────────
/** A part of Part workbench objects: its read() has OBJECTS (feature_edit_part.py). */
export const isPartDoc = (d: FeatureDoc | undefined | null): d is FeatureDoc => !!d && Array.isArray(d.objects)
export const objectOf = (doc: FeatureDoc | undefined, name: string) => doc?.objects?.find((o) => o.name === name)
/** Whether a tree reference ("part/Name") is a Part object (or a document-level sketch). */
export const isObjectRef = (s: State, ref: string) => { const [p, n] = splitRef(ref); return !!n && !!objectOf(s.features[p], n) }
export const labelOf = (o: Feature) => (typeof o.label === 'string' && o.label ? o.label : o.name)

/** Each type's tree icon (its ViewProvider's getIcon) and FreeCAD's short name. */
const TYPES: Record<string, [IconName, string]> = {
  'Part::Box': ['pt-box', 'Box'], 'Part::Cylinder': ['pt-cylinder', 'Cylinder'], 'Part::Sphere': ['pt-sphere', 'Sphere'],
  'Part::Cone': ['pt-cone', 'Cone'], 'Part::Torus': ['pt-torus', 'Torus'], 'Part::Tube': ['pt-tube', 'Tube'],
  'Part::Prism': ['pt-prism', 'Prism'], 'Part::Wedge': ['pt-wedge', 'Wedge'], 'Part::Helix': ['pt-helix', 'Helix'],
  'Part::Spiral': ['pt-spiral', 'Spiral'], 'Part::Ellipsoid': ['pt-ellipsoid', 'Ellipsoid'], 'Part::Plane': ['pt-plane', 'Plane'],
  'Part::Circle': ['pt-circle', 'Circle'], 'Part::Ellipse': ['pt-ellipse', 'Ellipse'], 'Part::Line': ['pt-line', 'Line'],
  'Part::Vertex': ['pt-point', 'Vertex'], 'Part::RegularPolygon': ['pt-polygon', 'RegularPolygon'], 'Part::Polygon': ['pt-polygon', 'Polygon'],
  'Part::Cut': ['pt-cut', 'Cut'], 'Part::Fuse': ['pt-fuse', 'Fuse'], 'Part::MultiFuse': ['pt-fuse', 'MultiFuse'],
  'Part::Common': ['pt-common', 'Common'], 'Part::MultiCommon': ['pt-common', 'MultiCommon'], 'Part::Section': ['pt-section', 'Section'],
  'Part::Extrusion': ['pt-extrude', 'Extrusion'], 'Part::Revolution': ['pt-revolve', 'Revolution'], 'Part::Mirroring': ['pt-mirror', 'Mirroring'],
  'Part::Fillet': ['pt-fillet', 'Fillet'], 'Part::Chamfer': ['pt-chamfer', 'Chamfer'], 'Part::Compound': ['pt-compound', 'Compound'],
  'Part::Refine': ['pt-feature', 'Refine'], 'Part::Loft': ['pt-loft', 'Loft'], 'Part::Sweep': ['pt-sweep', 'Sweep'],
  'Part::Offset': ['pt-offset', 'Offset'], 'Part::Offset2D': ['pt-offset2d', 'Offset2D'], 'Part::Thickness': ['pt-thickness', 'Thickness'],
  'Part::ProjectOnSurface': ['pt-projection', 'ProjectOnSurface'], 'Part::BooleanFragments': ['pt-fragments', 'BooleanFragments'],
  'Part::Slice': ['pt-slice', 'Slice'], 'Part::XOR': ['pt-xor', 'XOR'], 'Part::Connect': ['pt-connect', 'Connect'],
  'Part::Embed': ['pt-embed', 'Embed'], 'Part::Cutout': ['pt-cutout', 'Cutout'], 'Part::CompoundFilter': ['pt-compound-filter', 'CompoundFilter'],
  [SKETCH]: ['pd-sketch', 'Sketch'],
}
export const partIcon = (type: string): IconName => TYPES[type]?.[0] ?? 'pt-feature'
export const partKind = (type: string) => TYPES[type]?.[1] ?? type

const msg = (e: unknown) => (e instanceof Error ? e.message : String(e))
/** Document::getUniqueObjectName: the base, or base001, base002 … over the document's every name (and the Body). */
export function uniqueName(doc: FeatureDoc | undefined, base: string): string {
  const taken = new Set([...(doc?.objects ?? []).map((o) => o.name), ...(doc?.features ?? []).map((f) => f.name), ...(doc?.body ? ['Body'] : [])])
  if (!taken.has(base)) return base
  for (let i = 1; ; i++) { const n = `${base}${String(i).padStart(3, '0')}`; if (!taken.has(n)) return n }
}
/** Document::getUniqueObjectLabel, as a Label set by a command comes out: unique over the labels (DuplicateLabels off). */
export function uniqueLabel(doc: FeatureDoc | undefined, base: string): string {
  const taken = new Set((doc?.objects ?? []).map(labelOf))
  if (!taken.has(base)) return base
  for (let i = 1; ; i++) { const n = `${base}${String(i).padStart(3, '0')}`; if (!taken.has(n)) return n }
}

// ── the active document ──────────────────────────────────────────────────────────────────────────────────────────
/** The part module the Part commands work in (FreeCAD's active document): the part of what is selected (a tree row or the
 *  3D view's body), else the one the last Part command used, else the only Part document there is. */
let lastDoc: string | null = null
export function activeDoc(): string | null {
  const s = getState()
  const fromSel = s.featSel.map((r) => splitRef(r)[0]).find((p) => isPartDoc(s.features[p]))
  if (fromSel) return fromSel
  const fromScene = s.selected.map((n) => s.scene?.bodies.find((b) => b.name === n)?.part).find((p) => p && isPartDoc(s.features[p]))
  if (fromScene) return fromScene
  if (lastDoc && isPartDoc(s.features[lastDoc])) return lastDoc
  const docs = Object.keys(s.features).filter((p) => isPartDoc(s.features[p]))
  return docs.length === 1 ? docs[0] : null
}
/** The active document, or a new one (Std_New's "Unnamed", as FreeCAD has a document open before a command runs). */
export async function ensureDoc(): Promise<string | null> {
  const s = getState()
  if (!s.slug) { report('warn', 'Make or open a document first (File > New Document)'); openTask('newDocument', ''); return null }
  const have = activeDoc()
  if (have) return have
  const taken = new Set([...Object.keys(s.features), ...(s.scene?.bodies.map((b) => b.part ?? '') ?? [])])
  let name = 'Unnamed', n = 0
  while (taken.has(name)) name = `Unnamed${String(++n).padStart(3, '0')}`
  if (s.scriptToPyConsole) consoleLog('in', `cad feature new ${s.slug} ${name} --document`)
  try {
    const r = await api.cad(s.slug, ['feature', 'new', s.slug, name, '--document'])
    if (r.exit !== 0) { report('err', `New document: ${resultText(r)}`); return null }
    const doc = r.data?.doc as FeatureDoc
    setState((x) => ({ features: { ...x.features, [name]: doc } }))
    report('msg', `New document: parts/${name}.py`)
    loadHistory()
    lastDoc = name
    return name
  } catch (e) { report('err', `New document: ${msg(e)}`); return null }
}
/** The selected objects of a document, in selection order: tree rows, as Gui::Selection hands them to a command. */
export function selectedObjects(part: string): string[] {
  const s = getState()
  return s.featSel.map(splitRef).filter(([p, n]) => p === part && n && (objectOf(s.features[p], n) || n === 'Body' || s.features[p]?.features.some((f) => f.name === n))).map(([, n]) => n)
}
/** Add one object (FreeCAD's addObject in a command's transaction) and select it. */
export async function addObject(part: string, feature: Feature, transaction: string, more: FeatureOp[] = []): Promise<boolean> {
  lastDoc = part
  const done = await applyOps(part, [{ op: 'add', feature }, ...more], { name: transaction })
  if (!done) return false
  setState({ featSel: [refOf(part, feature.name)], selected: [] })
  return true
}

// ── the commands that act on the selection at once (Command.cpp, CommandParametric.cpp, BOPFeatures.py, ...) ────────
const warn = (title: string, text: string) => void messageBox('warning', title, text)
/** Part_Box … Part_Torus (CmdPartBox::activated …): the object with its defaults, named and labelled as the command does. */
async function primitive(type: string, base: string, label: string) {
  const part = await ensureDoc()
  if (!part) return
  const doc = getState().features[part]
  const name = uniqueName(doc, base)
  const lab = uniqueLabel(doc, label)
  await addObject(part, { name, type, ...(lab !== name ? { label: lab } : {}) }, label)
}
async function booleanOf(kind: 'cut' | 'fuse' | 'common' | 'section') {
  const part = activeDoc()
  const sel = part ? selectedObjects(part) : []
  const doc = part ? getState().features[part] : undefined
  if (kind === 'cut' || kind === 'section') {
    if (sel.length !== 2) return warn('Wrong selection', 'Select two shapes please.')
    const [type, base, tx] = kind === 'cut' ? ['Part::Cut', 'Cut', 'Part Cut'] : ['Part::Section', 'Section', 'Section']
    return void addObject(part!, { name: uniqueName(doc, base), type, base: sel[0], tool: sel[1] }, tx)
  }
  if (kind === 'fuse' && sel.length < 2 && !(sel.length === 1 && await compoundChildren(part!, sel[0]) >= 2)) {
    return warn('Wrong Selection', 'Select at least 2 shapes. Alternatively, select 1 compound containing 2 or more shapes to be fused.')
  }
  if (kind === 'common' && !sel.length) {
    return warn('Wrong Selection', 'Select at least 2 shapes. Alternatively, select 1 compound containing 2 or more shapes to compute the intersection between.')
  }
  const [type, base, tx] = kind === 'fuse' ? ['Part::MultiFuse', 'Fusion', 'Fusion'] : ['Part::MultiCommon', 'Common', 'Common']
  await addObject(part!, { name: uniqueName(doc, base), type, shapes: sel }, tx)
}
/** How many shapes a compound object holds (its first level), from the server's build of it. */
async function compoundChildren(part: string, name: string): Promise<number> {
  const s = getState()
  if (!s.slug) return 0
  try { const r = await api.featureShape(s.slug, part, [], name); return Number(r.data?.children ?? 0) } catch { return 0 }
}
/** Part_Compound, Part_RefineShape, the split, join and compound tools (their commands in BOPTools and CompoundTools). */
async function fromSelection(cmd: string) {
  const part = activeDoc()
  const sel = part ? selectedObjects(part) : []
  const doc = part ? getState().features[part] : undefined
  const need = (n: number, text: string) => { if (sel.length < n) { warn('Wrong selection', text); return false } return true }
  const add = (base: string, type: string, props: Record<string, unknown>, tx: string) =>
    addObject(part!, { name: uniqueName(doc, base), type, ...props }, tx)
  switch (cmd) {
    case 'Part_Compound': if (need(1, 'Select one shape or more, please.')) await add('Compound', 'Part::Compound', { links: sel }, 'Compound'); return
    case 'Part_RefineShape':
      if (!need(1, 'Select one shape or more, please.')) return
      for (const n of sel) await addObject(part!, { name: uniqueName(getState().features[part!], n), type: 'Part::Refine', source: n }, 'Refine shape')
      return
    case 'Part_BooleanFragments':
      if (need(1, 'Select at least one object, or one or more compounds')) await add('BooleanFragments', 'Part::BooleanFragments', { objects: sel }, 'Create Boolean Fragments'); return
    case 'Part_Slice':
      if (sel.length < 2) return warn('Bad selection', 'Select at least two objects, or one or more compounds. The first one is the object to be sliced, the rest are the slicing objects.')
      await add('Slice', 'Part::Slice', { base: sel[0], tools: sel.slice(1), mode: 'Split' }, 'Create Slice'); return
    case 'Part_SliceApart': {
      if (sel.length < 2) return warn('Bad selection', 'Select at least two objects. The first one is the object to be sliced, the rest are the slicing objects.')
      const name = uniqueName(doc, 'Slice')
      if (!await addObject(part!, { name, type: 'Part::Slice', base: sel[0], tools: sel.slice(1), mode: 'Split' }, 'Slice apart')) return
      return explode(part!, name, 'Slice apart')
    }
    case 'Part_XOR': if (need(1, 'Select at least two objects, or one or more compounds.')) await add('XOR', 'Part::XOR', { objects: sel }, 'Create Boolean XOR'); return
    case 'Part_JoinConnect': if (need(1, 'Select at least one object, or one or more compounds')) await add('Connect', 'Part::Connect', { objects: sel }, 'Create Connect'); return
    case 'Part_JoinEmbed': case 'Part_JoinCutout': {
      if (sel.length !== 2) return warn('Bad selection', cmd === 'Part_JoinEmbed' ? 'Select base object, then the object to embed, and then invoke this tool.' : 'Select the object to make a cutout in, then the object that should fit into the cutout, and then invoke this tool.')
      const [base, type, tx] = cmd === 'Part_JoinEmbed' ? ['Embed', 'Part::Embed', 'Create Embed'] : ['Cutout', 'Part::Cutout', 'Create Cutout']
      await add(base, type, { base: sel[0], tool: sel[1] }, tx); return
    }
    case 'Part_CompoundFilter': {
      if (sel.length < 1 || sel.length > 2) return warn('First select a shape that is a compound. If a second object is selected (optional) it will be treated as a stencil.', '')
      const props = sel.length === 2 ? { base: sel[0], stencil: sel[1], filter_type: 'collision-pass' } : { base: sel[0], filter_type: 'window-volume' }
      await add('CompoundFilter', 'Part::CompoundFilter', props, 'Create CompoundFilter'); return
    }
    case 'Part_ExplodeCompound':
      if (sel.length !== 1) return warn('Bad selection', 'Select a single compound, please.')
      return explode(part!, sel[0], 'Explode')
  }
}
/** CompoundTools.Explode.explodeCompound: a CompoundFilter for each child, "specific items" with its index, labelled
 *  "<Label>.<i>" (FreeCAD also groups them in "Exploded <Label>"; a part file has no groups). */
async function explode(part: string, name: string, tx: string) {
  const n = await compoundChildren(part, name)
  if (!n) { report('err', `${tx}: ${name} has no shapes to explode`); return }
  const doc = getState().features[part]
  const label = labelOf(objectOf(doc, name) ?? { name, type: '' })
  const ops: FeatureOp[] = []
  for (let i = 0; i < n; i++) ops.push({ op: 'add', feature: { name: `${name}_child${i}`, type: 'Part::CompoundFilter', base: name, filter_type: 'specific items', items: String(i), label: `${label}.${i}` } })
  if (await applyOps(part, ops, { name: tx })) setState({ featSel: [refOf(part, `${name}_child0`)], selected: [] })
}

// ── the menu and the toolbars (PartGui::Workbench::setupMenuBar / setupToolBars) ─────────────────────────────────────
const NA = (label: string, icon: IconName, cmd: string, why: string): Entry => ({ label, icon, cmd, disabled: true, title: `n/a: ${why}` })
const STATIC = 'it makes a Part::Feature holding a fixed copy of a shape, which a part file of parametric objects cannot hold'
const MESH = 'there are no meshes in a part file'
function partState() {
  const s = getState(), part = activeDoc()
  return { s, part, sel: part ? selectedObjects(part) : [], doc: !!s.slug }
}
/** Part's "&Part" menu, entry by entry as the real FreeCAD 26.3 has it (ui/scripts/fcpart.json). */
export function partMenu(): Entry[] {
  const { sel, doc, part } = partState()
  const n = sel.length
  // Part_EditAttachment's IsActive: exactly one selected object, and one with a Placement (a Part document's objects
  // here; a Body feature has none, and a sketch's owner is the Sketcher)
  const one = n === 1 ? objectOf(getState().features[part ?? ''], sel[0]) : undefined
  const attachable = !!one && one.type !== SKETCH
  return [
    NA('Box Selection', 'pt-box-selection', 'Part_BoxSelection', 'face picking by a box is not in the 3D view yet'),
    'sep',
    { label: 'Primitives', sub: primitiveEntries() },
    { label: 'Primitive', icon: 'pt-primitives', cmd: 'Part_Primitives', disabled: !doc, onSelect: () => void openPart('primitives') },
    NA('Shape Builder', 'pt-builder', 'Part_Builder', STATIC),
    'sep',
    NA('Shape From Mesh', 'pt-shape-from-mesh', 'Part_ShapeFromMesh', MESH),
    NA('Points From Shape', 'pt-points-from-mesh', 'Part_PointsFromMesh', MESH),
    NA('Convert to Solid', 'pt-make-solid', 'Part_MakeSolid', STATIC),
    NA('Reverse Shapes', 'pt-reverse', 'Part_ReverseShape', 'Part::Reverse is not ported yet'),
    { label: 'Copy', sub: [
      NA('Simple Copy', 'pt-feature', 'Part_SimpleCopy', STATIC), NA('Transformed Copy', 'pt-transformed-copy', 'Part_TransformedCopy', STATIC),
      NA('Shape Element Copy', 'pt-element-copy', 'Part_ElementCopy', STATIC),
      { label: 'Refine Shape', icon: 'pt-refine', cmd: 'Part_RefineShape', disabled: !n, onSelect: () => void fromSelection('Part_RefineShape') }] },
    'sep',
    { label: 'Boolean', sub: [
      { label: 'Boolean Operation', icon: 'pt-booleans', cmd: 'Part_Boolean', disabled: !doc, onSelect: () => void openPart('boolean') },
      { label: 'Cut', icon: 'pt-cut', cmd: 'Part_Cut', disabled: n !== 2, onSelect: () => void booleanOf('cut') },
      { label: 'Union', icon: 'pt-fuse', cmd: 'Part_Fuse', disabled: !n, onSelect: () => void booleanOf('fuse') },
      { label: 'Intersection', icon: 'pt-common', cmd: 'Part_Common', disabled: !n, onSelect: () => void booleanOf('common') }] },
    { label: 'Join', sub: joinEntries() },
    { label: 'Split', sub: splitEntries() },
    { label: 'Compound', sub: compoundEntries() },
    'sep',
    { label: 'New Sketch', icon: 'pd-new-sketch', cmd: 'Sketcher_NewSketch', disabled: !doc, onSelect: () => void openPart('sketch') },
    ...toolEntries(),
    'sep',
    { label: 'Attachment', icon: 'pt-attachment', cmd: 'Part_EditAttachment', disabled: !attachable,
      onSelect: () => { if (part && one) openTask('attach', part, one.name) } },
    'sep',
    NA('Check Geometry', 'pt-check-geometry', 'Part_CheckGeometry', 'the checks (Recompute) judge the geometry here'),
    NA('Defeaturing', 'pt-defeaturing', 'Part_Defeaturing', STATIC),
    NA('Inspect Appearance', 'material', 'Materials_InspectAppearance', 'materials are set in the part\'s source'),
    NA('Inspect Material', 'material', 'Materials_InspectMaterial', 'materials are set in the part\'s source'),
  ]
}
function primitiveEntries(): Entry[] {
  const doc = !!getState().slug
  return [
    { label: 'Cube', icon: 'pt-box', cmd: 'Part_Box', disabled: !doc, onSelect: () => void primitive('Part::Box', 'Box', 'Cube') },
    { label: 'Cylinder', icon: 'pt-cylinder', cmd: 'Part_Cylinder', disabled: !doc, onSelect: () => void primitive('Part::Cylinder', 'Cylinder', 'Cylinder') },
    { label: 'Sphere', icon: 'pt-sphere', cmd: 'Part_Sphere', disabled: !doc, onSelect: () => void primitive('Part::Sphere', 'Sphere', 'Sphere') },
    { label: 'Cone', icon: 'pt-cone', cmd: 'Part_Cone', disabled: !doc, onSelect: () => void primitive('Part::Cone', 'Cone', 'Cone') },
    { label: 'Torus', icon: 'pt-torus', cmd: 'Part_Torus', disabled: !doc, onSelect: () => void primitive('Part::Torus', 'Torus', 'Torus') },
    { label: 'Tube', icon: 'pt-tube', cmd: 'Part_Tube', disabled: !doc, onSelect: () => void openPart('tube') },
  ]
}
function joinEntries(): Entry[] {
  const n = partState().sel.length
  return [
    { label: 'Connect Shapes', icon: 'pt-connect', cmd: 'Part_JoinConnect', disabled: !n, onSelect: () => void fromSelection('Part_JoinConnect') },
    { label: 'Embed Shapes', icon: 'pt-embed', cmd: 'Part_JoinEmbed', disabled: !n, onSelect: () => void fromSelection('Part_JoinEmbed') },
    { label: 'Cutout Shape', icon: 'pt-cutout', cmd: 'Part_JoinCutout', disabled: !n, onSelect: () => void fromSelection('Part_JoinCutout') },
  ]
}
function splitEntries(): Entry[] {
  const n = partState().sel.length
  return [
    { label: 'Boolean Fragments', icon: 'pt-fragments', cmd: 'Part_BooleanFragments', disabled: !n, onSelect: () => void fromSelection('Part_BooleanFragments') },
    { label: 'Slice Apart', icon: 'pt-slice-apart', cmd: 'Part_SliceApart', disabled: !n, onSelect: () => void fromSelection('Part_SliceApart') },
    { label: 'Slice to Compound', icon: 'pt-slice', cmd: 'Part_Slice', disabled: !n, onSelect: () => void fromSelection('Part_Slice') },
    { label: 'Boolean XOR', icon: 'pt-xor', cmd: 'Part_XOR', disabled: !n, onSelect: () => void fromSelection('Part_XOR') },
  ]
}
function compoundEntries(): Entry[] {
  const n = partState().sel.length
  return [
    { label: 'Compound', icon: 'pt-compound', cmd: 'Part_Compound', disabled: !n, onSelect: () => void fromSelection('Part_Compound') },
    { label: 'Explode Compound', icon: 'pt-explode', cmd: 'Part_ExplodeCompound', disabled: n !== 1, onSelect: () => void fromSelection('Part_ExplodeCompound') },
    { label: 'Compound Filter', icon: 'pt-compound-filter', cmd: 'Part_CompoundFilter', disabled: !n, onSelect: () => void fromSelection('Part_CompoundFilter') },
    NA('Set Tolerance', 'pt-feature', 'Part_ToleranceSet', 'shape tolerances are OCCT\'s defaults here'),
  ]
}
/** The Part menu's tools from New Sketch on (and the Part Tools toolbar's). */
function toolEntries(): Entry[] {
  const { sel, doc } = partState()
  const n = sel.length
  return [
    { label: 'Extrude', icon: 'pt-extrude', cmd: 'Part_Extrude', disabled: !doc, onSelect: () => void openPart('extrude') },
    { label: 'Revolve', icon: 'pt-revolve', cmd: 'Part_Revolve', disabled: !doc, onSelect: () => void openPart('revolve') },
    { label: 'Mirror', icon: 'pt-mirror', cmd: 'Part_Mirror', disabled: !doc, onSelect: () => void openPart('mirror') },
    NA('Scale', 'pt-scale', 'Part_Scale', 'Part::Scale is not ported yet'),
    { label: 'Fillet', icon: 'pt-fillet', cmd: 'Part_Fillet', disabled: !doc, onSelect: () => void openPart('fillet') },
    { label: 'Chamfer', icon: 'pt-chamfer', cmd: 'Part_Chamfer', disabled: !doc, onSelect: () => void openPart('chamfer') },
    NA('Face From Wires', 'pt-make-face', 'Part_MakeFace', 'Part::Face is not ported yet'),
    NA('Ruled Surface', 'pt-ruled', 'Part_RuledSurface', 'Part::RuledSurface is not ported yet'),
    { label: 'Loft', icon: 'pt-loft', cmd: 'Part_Loft', disabled: !doc, onSelect: () => void openPart('loft') },
    { label: 'Sweep', icon: 'pt-sweep', cmd: 'Part_Sweep', disabled: !doc, onSelect: () => void openPart('sweep') },
    { label: 'Section', icon: 'pt-section', cmd: 'Part_Section', disabled: n !== 2, onSelect: () => void booleanOf('section') },
    NA('Cross-Sections', 'pt-cross-sections', 'Part_CrossSections', STATIC),
    { label: '3D Offset', icon: 'pt-offset', cmd: 'Part_Offset', disabled: n !== 1, onSelect: () => void openPart('offset') },
    { label: '2D Offset', icon: 'pt-offset2d', cmd: 'Part_Offset2D', disabled: n !== 1, onSelect: () => void openPart('offset2d') },
    { label: 'Thickness', icon: 'pt-thickness', cmd: 'Part_Thickness', disabled: n !== 1, onSelect: () => void openPart('thickness') },
    { label: 'Project on Surface', icon: 'pt-projection', cmd: 'Part_ProjectionOnSurface', disabled: !doc, onSelect: () => void openPart('projection') },
    NA('Persistent Section Cut', 'pt-section-cut', 'Part_SectionCut', 'View > Clipping plane cuts the view here'),
  ]
}
/** The workbench's toolbars, button by button (setupToolBars): a group's tool button shows its default command. */
export function partToolbars(): [string, Entry[]][] {
  const m = partMenu(), tools = toolEntries()
  const by = (list: Entry[], cmd: string) => list.find((e): e is Exclude<Entry, 'sep'> => e !== 'sep' && e.cmd === cmd)!
  const sub = (label: string) => (m.find((e) => e !== 'sep' && e.label === label) as Exclude<Entry, 'sep'>).sub!
  const bool = sub('Boolean')
  const offsets = [by(tools, 'Part_Offset'), by(tools, 'Part_Offset2D')]
  return [
    ['Solids', [...primitiveEntries(), by(m, 'Part_Primitives'), by(m, 'Part_Builder')]],
    ['Part Tools', [by(m, 'Sketcher_NewSketch'), ...tools.filter((e) => e !== 'sep' && !['Part_Offset', 'Part_Offset2D', 'Part_SectionCut'].includes(e.cmd ?? '')).slice(0, 12),
      { label: '3D Offset', icon: 'pt-offset', cmd: 'Part_CompOffset', sub: offsets, disabled: offsets.every((e) => e.disabled) },
      by(tools, 'Part_Thickness'), by(tools, 'Part_ProjectionOnSurface'),
      NA('Appearance per Face', 'pt-color-face', 'Part_ColorPerFace', 'face colours are the material\'s here')]],
    ['Boolean Tools', [{ label: 'Compound', icon: 'pt-compound', cmd: 'Part_CompCompoundTools', sub: compoundEntries() }, ...bool,
      { label: 'Connect Shapes', icon: 'pt-connect', cmd: 'Part_CompJoinFeatures', sub: joinEntries() },
      { label: 'Boolean Fragments', icon: 'pt-fragments', cmd: 'Part_CompSplitFeatures', sub: splitEntries() },
      by(m, 'Part_CheckGeometry'), by(m, 'Part_Defeaturing')]],
  ]
}
/** The Part menu and toolbars as plain data (labels, commands, greyed or not, submenus): what partcheck.mjs holds to
 *  FreeCAD's (cadui.part() in the page). */
export function partMenus() {
  const plain = (es: Entry[]): unknown[] => es.map((e) => (e === 'sep' ? { sep: true } : { text: e.label, cmd: e.cmd ?? null, enabled: !e.disabled, ...(e.sub ? { menu: plain(e.sub) } : {}) }))
  return { part: plain(partMenu()), toolbars: partToolbars().map(([title, es]) => ({ title, buttons: plain(es) })) }
}
/** The registry's entries (cmdreg.ts): every Part command by its FreeCAD name. */
export function partCommands(): [string, Exclude<Entry, 'sep'>][] {
  const out: [string, Exclude<Entry, 'sep'>][] = []
  const walk = (es: Entry[]) => { for (const e of es) { if (e === 'sep') continue; if (e.cmd && e.onSelect && !out.some(([c]) => c === e.cmd)) out.push([e.cmd, e]); if (e.sub) walk(e.sub) } }
  walk(partMenu())
  return out
}
/** A Part command run by its name (Customize, shortcuts, macros), read fresh: its state follows the selection. */
export const partRun = (cmd: string) => partCommands().find(([c]) => c === cmd)?.[1].onSelect?.()
export const partEnabled = (cmd: string) => { const e = partCommands().find(([c]) => c === cmd)?.[1]; return !!e && !e.disabled }

// ── the task panels (part_tasks.tsx) ───────────────────────────────────────────────────────────────────────────────
/** A Part command's panel: `other` is "<which>" or "<which>:<object>" (an object edited). */
export async function openPart(which: string, edit?: string) {
  const part = which === 'primitives' || which === 'tube' || which === 'sketch' || which === 'boolean' ? await ensureDoc() : activeDoc()
  if (!part) { if (which !== 'primitives') warn('Wrong selection', 'Select the object to work on in the tree, please.'); return }
  lastDoc = part
  openTask('part', part, edit ? `${which}:${edit}` : which)
}
/** Std_Edit, a double-click: a primitive's Primitives panel, an Extrude's, ... panel; a sketch opens in the Sketcher. */
const EDIT: Record<string, string> = {
  'Part::Extrusion': 'extrude', 'Part::Revolution': 'revolve', 'Part::Mirroring': 'mirror', 'Part::Fillet': 'fillet', 'Part::Chamfer': 'chamfer',
  'Part::Loft': 'loft', 'Part::Sweep': 'sweep', 'Part::Offset': 'offset', 'Part::Offset2D': 'offset2d', 'Part::Thickness': 'thickness',
  'Part::Tube': 'tube', 'Part::ProjectOnSurface': 'projection',
}
const PRIMITIVE_TYPES = ['Part::Plane', 'Part::Box', 'Part::Cylinder', 'Part::Cone', 'Part::Sphere', 'Part::Ellipsoid', 'Part::Torus', 'Part::Prism',
  'Part::Wedge', 'Part::Helix', 'Part::Spiral', 'Part::Circle', 'Part::Ellipse', 'Part::Vertex', 'Part::Line', 'Part::RegularPolygon']
export function editObject(part: string, name: string) {
  const o = objectOf(getState().features[part], name)
  if (!o) return
  if (o.type === SKETCH) return editSketch(part, name)
  lastDoc = part
  if (PRIMITIVE_TYPES.includes(o.type)) return openTask('part', part, `primitives:${name}`)
  if (EDIT[o.type]) return openTask('part', part, `${EDIT[o.type]}:${name}`)
  report('msg', `${labelOf(o)}: a ${partKind(o.type)} has no task panel; edit it in the property view`)
}

// ── edits from the tree: Space, Delete, F2 ─────────────────────────────────────────────────────────────────────────
/** Std_ToggleVisibility on objects: their ViewObject.Visibility, written as the part file's visibility= (one step each). */
export async function toggleObjects(refs: string[], to?: boolean) {
  const s = getState()
  const byPart = new Map<string, FeatureOp[]>()
  for (const r of refs) {
    const [p, n] = splitRef(r)
    const doc = s.features[p]
    const o = objectOf(doc, n)
    if (!o) continue
    if (o.type === SKETCH) { setState((x) => ({ sketchShown: x.sketchShown.includes(r) ? x.sketchShown.filter((y) => y !== r) : [...x.sketchShown, r] })); continue }
    const shown = doc?.object_tree?.shown.includes(n) ?? true
    const want = to ?? !shown
    if (want === shown) continue
    byPart.set(p, [...(byPart.get(p) ?? []), { op: 'set', name: n, props: { visibility: want } }])
  }
  for (const [p, ops] of byPart) await applyOps(p, ops, { name: 'Toggle visibility' })
}
/** Std_Delete: an object no other uses goes; one that another uses brings FreeCAD's question, and stays (a part file has
 *  no broken links). */
export async function deleteObjects(refs: string[]) {
  const s = getState()
  for (const [p, names] of groupByPart(refs)) {
    const doc = s.features[p]
    const users = (doc?.objects ?? []).filter((o) => !names.includes(o.name) && names.some((n) => (doc?.object_tree?.children[o.name] ?? []).includes(n) || JSON.stringify(o).includes(`"${n}"`)))
    if (users.length) {
      const yes = await messageBox('warning', 'Object Dependencies', `The following referencing objects might break.\n\nContinue?\n\n${users.map(labelOf).join('\n')}`, ['Yes', 'No'])
      if (yes !== 'Yes') continue
      report('err', `Delete: ${users.map(labelOf).join(', ')} would be left with a broken link, which a part file cannot hold; delete ${users.length > 1 ? 'them' : 'it'} first`)
      continue
    }
    await applyOps(p, names.map((n) => ({ op: 'delete', name: n })), { name: 'Delete' })
  }
  setState({ featSel: [] })
}
const groupByPart = (refs: string[]) => {
  const m = new Map<string, string[]>()
  for (const r of refs) { const [p, n] = splitRef(r); if (n) m.set(p, [...(m.get(p) ?? []), n]) }
  return m
}
let renaming: string | null = null
const renameSubs = new Set<() => void>()
/** F2 on a row: FreeCAD renames the Label, the Name stays. */
export function startRenameObject(ref: string) { renaming = ref; renameSubs.forEach((f) => f()) }
async function finishRenameObject(ref: string, label: string | null) {
  renaming = null
  renameSubs.forEach((f) => f())
  if (label === null) return
  const [p, n] = splitRef(ref)
  const o = objectOf(getState().features[p], n)
  if (!o || !label || label === labelOf(o)) return
  await applyOps(p, [{ op: 'set', name: n, props: { label: label === n ? null : label } }], { name: `Rename ${n}.Label` })
}
/** App.tsx's key handler asks partdesign.tsx's featureKey, which asks here first for Part objects' rows. */
export function partKey(e: KeyboardEvent): boolean {
  const s = getState()
  const refs = s.featSel.filter((r) => isObjectRef(s, r))
  if (!refs.length || refs.length !== s.featSel.length) return false
  const t = e.target as HTMLElement | null
  if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return false
  if (e.key === 'F2') { startRenameObject(refs[0]); return true }
  if (e.key === 'Delete' || e.key === 'Backspace') { void deleteObjects(refs); return true }
  if (e.key === ' ') { void toggleObjects(refs); return true }
  if (e.key === 'Enter' && refs.length === 1) { editObject(...splitRef(refs[0])); return true }
  return false
}

/** A document sketch is shown until an object that hides its input uses it (the server's sketches_shown); Space flips that. */
export const sketchShownOf = (s: State, part: string, name: string) =>
  (s.features[part]?.object_tree?.sketches_shown ?? []).includes(name) !== s.sketchShown.includes(refOf(part, name))

// ── the tree ───────────────────────────────────────────────────────────────────────────────────────────────────────
const open = new Map<string, boolean>()
const openSubs = new Set<() => void>()
function pick(ref: string, additive: boolean) {
  const s = getState()
  setState({ featSel: additive ? (s.featSel.includes(ref) ? s.featSel.filter((r) => r !== ref) : [...s.featSel, ref]) : [ref], selected: [], subSel: [] })
  picker?.(ref)
}
/** While a task panel picks objects from the tree (Mirror's reference, Loft's profiles), a click hands it the row. */
let picker: ((ref: string) => void) | null = null
export function setObjectPicker(f: ((ref: string) => void) | null) { picker = f }

function ObjRow({ ctx, depth, refKey, icon, label, internal, desc, hidden, kids, onDouble }:
  { ctx: TreeCtx; depth: number; refKey: string; icon: IconName; label: string; internal: string; desc?: string; hidden: boolean; kids: boolean; onDouble?(): void }) {
  const sel = useStore((s) => s.featSel.includes(refKey))
  const [, redraw] = useState(0)
  useEffect(() => { const f = () => redraw((n) => n + 1); renameSubs.add(f); openSubs.add(f); return () => { renameSubs.delete(f); openSubs.delete(f) } }, [])
  const opened = open.get(refKey) ?? true
  return (
    <div className={cls('trow', 'pdrow', 'ptrow', sel && 'sel', hidden && 'hid')} data-ref={refKey}
      onClick={(e) => { ctx.cancelPreselect(); pick(refKey, e.metaKey || e.ctrlKey) }} onDoubleClick={() => onDouble?.()}
      onMouseEnter={() => ctx.enter(null)}
      onContextMenu={(e) => { e.preventDefault(); e.stopPropagation(); if (!getState().featSel.includes(refKey)) pick(refKey, false); ctx.menu({ x: e.clientX, y: e.clientY }) }}>
      <span className="tlab">
        <span className="pdindent" style={{ width: 6 + 12 * (depth - 1) }} />
        {kids ? <Twisty open={opened} onClick={() => { open.set(refKey, !opened); openSubs.forEach((f) => f()) }} /> : <span className="twisty-none" />}
        {ctx.checkBoxes && <input type="checkbox" className="tcheckbox" checked={sel} onClick={(e) => e.stopPropagation()} onChange={() => pick(refKey, true)} />}
        {ctx.eyes && <span className="teye" title="Toggle visibility (Space)" onClick={(e) => { e.stopPropagation(); void toggleObjects([refKey]) }}
          onDoubleClick={(e) => e.stopPropagation()}><Icon name={hidden ? 'eye-off' : 'eye'} size={ctx.iconSize} /></span>}
        <span className="ticon"><Icon name={icon} size={ctx.iconSize} /></span>
        {renaming === refKey
          ? <input className="trename" autoFocus defaultValue={label} onClick={(e) => e.stopPropagation()} onBlur={(e) => void finishRenameObject(refKey, e.currentTarget.value.trim())}
            onKeyDown={(e) => { e.stopPropagation(); if (e.key === 'Enter') e.currentTarget.blur(); if (e.key === 'Escape') void finishRenameObject(refKey, null) }} />
          : <span className="tname">{label}</span>}
      </span>
      {ctx.showDesc && <span className="tdesc">{desc ?? ''}</span>}
      {ctx.showInternal && <span className="tdesc">{internal}</span>}
    </div>
  )
}

/** A Part document in the tree: its part module's row, then the objects nothing claims, each with what it claims under it
 *  (ViewProvider::claimChildren: a Cut's Base and Tool, an Extrude's sketch), the hidden ones greyed as Tree.cpp greys an
 *  invisible object; the Body, when the part has one, through partdesign.tsx's rows (bodyRows). */
export function PartDocRows({ ctx, part, row, bodyRows }: { ctx: TreeCtx; part: string; row(children: ReactNode): ReactNode; bodyRows(depth: number): ReactNode }) {
  const s = useStore((x) => x)
  const [, redraw] = useState(0)
  useEffect(() => { const f = () => redraw((n) => n + 1); openSubs.add(f); return () => { openSubs.delete(f) } }, [])
  const doc = s.features[part]
  if (!isPartDoc(doc)) return null
  const tree = doc.object_tree ?? { children: {}, top: (doc.objects ?? []).map((o) => o.name), shown: [], hidden: [] }
  const docRef = refOf(part, '')
  const opened = open.get(docRef) ?? true
  const twisty = <Twisty open={opened} onClick={() => { open.set(docRef, !opened); openSubs.forEach((f) => f()) }} />
  const objRow = (name: string, depth: number, seen: Set<string>): ReactNode => {
    if (name === 'Body') return <div key={`${part}/Body/${depth}`}>{bodyRows(depth)}</div>
    const o = objectOf(doc, name)
    const r = refOf(part, name)
    if (!o) return <ObjRow key={r + depth} ctx={ctx} depth={depth} refKey={r} icon="part" label={name} internal={name} hidden={false} kids={false} desc="a feature of the Body" />
    const kids = (tree.children[name] ?? []).filter((k) => !seen.has(k))
    const hidden = o.type === SKETCH ? sketchShownOf(s, part, name) === false : !tree.shown.includes(name)
    const next = new Set([...seen, name])
    return (
      <div key={r + depth} className="pdgroup">
        <ObjRow ctx={ctx} depth={depth} refKey={r} icon={partIcon(o.type)} label={labelOf(o)} internal={o.name} desc={partKind(o.type)}
          hidden={hidden} kids={kids.length > 0} onDouble={() => editObject(part, name)} />
        {kids.length > 0 && (open.get(r) ?? true) && kids.map((k) => objRow(k, depth + 1, next))}
      </div>
    )
  }
  return <>{row(twisty)}{opened && tree.top.map((n) => objRow(n, 2, new Set()))}</>
}

/** The tree's context menu on a Part object's row (TreeWidget::contextMenuEvent with PartGui::Workbench's, as the real
 *  FreeCAD 26.3 shows it on a Cut: ui/scripts/fcpart.json's menu_cut). */
export function partTreeEntries(common: { expressionActions: Entry; linkActions: Entry; showHidden: Entry; properties(): void }): Entry[] {
  const s = getState(), refs = s.featSel.filter((r) => isObjectRef(s, r))
  const na = (label: string, why: string, extra: Partial<Exclude<Entry, 'sep'>> = {}): Entry => ({ label, disabled: true, title: `n/a: ${why}`, ...extra })
  const appearance = 'colours are the part\'s material here'
  return [
    na('Appearance per Face', appearance, { icon: 'pt-color-face' }),
    'sep',
    na('Toggle Freeze', 'parts rebuild from source; there is no recompute to freeze', { icon: 'freeze' }),
    'sep',
    { label: 'Toggle Visibility', kbd: 'Space', icon: 'visibility', onSelect: () => void toggleObjects(refs) },
    { label: 'Show Selection', icon: 'show-sel', onSelect: () => void toggleObjects(refs, true) },
    { label: 'Hide Selection', icon: 'hide', onSelect: () => void toggleObjects(refs, false) },
    na('Toggle Selectability', 'the 3D view picks the part\'s shape', { icon: 'unselectable' }),
    na('Select All Instances', 'an object has one instance'),
    'sep',
    na('Material', 'materials are set in the part\'s source', { icon: 'material' }),
    na('Appearance', appearance, { icon: 'appearance', kbd: '⌘D' }),
    na('Random Color', appearance, { icon: 'random-color' }),
    na('Toggle Transparency', appearance, { icon: 'transparency', kbd: 'V, T' }),
    'sep',
    { label: 'Cut', kbd: '⌘X', icon: 'edit-cut', disabled: true },
    { label: 'Copy', kbd: '⌘C', icon: 'edit-copy', onSelect: () => { void navigator.clipboard?.writeText(refs.map((r) => splitRef(r)[1]).join('\n')) } },
    { label: 'Paste', kbd: '⌘V', icon: 'edit-paste', disabled: true },
    { label: 'Delete', kbd: '⌫', icon: 'edit-delete', cmd: 'Std_Delete', disabled: !refs.length, onSelect: () => void deleteObjects(refs) },
    { label: 'Send to Console', kbd: '⇧⌘P', icon: 'console', onSelect: () => consoleLog('in', refs.map((r) => splitRef(r).join('.')).join(' ')) },
    na('Transform', 'an object is placed by its placement= in the property view', { icon: 'transform' }),
    na('Placement', 'an object is placed by its placement= in the property view', { icon: 'placement' }),
    { label: 'Properties', kbd: '⌥↵', onSelect: common.properties },
    'sep',
    common.expressionActions, common.linkActions, common.showHidden,
    na('Toggle Visibility in Tree View', 'a document\'s rows always show'),
    na('Add Dependent Objects to Selection', 'the objects that use one show under it'),
    'sep',
    { label: 'Mark to Recompute', icon: 'recompute', onSelect: () => void loadFeatures() },
    { label: 'Recompute Object', kbd: '⇧⌘R', icon: 'recompute', onSelect: () => void loadFeatures() },
    'sep',
    { label: 'Rename', kbd: 'F2', disabled: refs.length !== 1, onSelect: () => startRenameObject(refs[0]) },
  ]
}

// ── the property view (PropertyEditor: groups in name order, FreeCAD's display names) ───────────────────────────────
const human = (camel: string) => camel.replace(/([a-z0-9])([A-Z])/g, '$1 $2').replace(/([A-Z])([A-Z][a-z])/g, '$1 $2')
const LEN = [1, 0, 0, 0, 0, 0, 0, 0] as quantity.Quantity['dims']
const ANG = [0, 0, 0, 0, 0, 0, 0, 1] as quantity.Quantity['dims']
const qtext = (n: number | null, dims: quantity.Quantity['dims']) => (n === null ? '?' : quantity.userString({ value: n, dims }).text)
const linkText = (v: unknown): string => {
  if (v == null) return ''
  if (typeof v === 'string') return v
  if (Array.isArray(v) && v.length === 2 && typeof v[0] === 'string' && !Array.isArray(v[0])) return `${v[0]} (${Array.isArray(v[1]) ? v[1].join(', ') : v[1]})`
  if (Array.isArray(v)) return `[${v.map(linkText).join(', ')}]`
  return JSON.stringify(v)
}
/** placement ((x, y, z), (yaw, pitch, roll)) as PropertyPlacementItem shows it: [(axis); angle; (position)]. */
function placementText(pl: unknown): string {
  const [pos, ypr] = Array.isArray(pl) ? (pl as number[][]) : [[0, 0, 0], [0, 0, 0]]
  const e = new THREE.Euler(THREE.MathUtils.degToRad(ypr[2] ?? 0), THREE.MathUtils.degToRad(ypr[1] ?? 0), THREE.MathUtils.degToRad(ypr[0] ?? 0), 'ZYX')
  const q = new THREE.Quaternion().setFromEuler(e)
  const angle = 2 * Math.acos(Math.min(1, Math.abs(q.w)))
  const s = Math.sqrt(Math.max(0, 1 - q.w * q.w)) * Math.sign(q.w || 1)
  const axis = s < 1e-9 ? [0, 0, 1] : [q.x / s, q.y / s, q.z / s]
  return `[(${axis.map((x) => x.toFixed(2)).join(' ')}); ${THREE.MathUtils.radToDeg(angle).toFixed(2)}°; (${pos.map((x) => `${(x ?? 0).toFixed(2)} mm`).join('  ')})]`
}
/** A Part object's Data tab: PART_PROPS's rows (FreeCAD's own, from fcpart.json), each value from the object's dict,
 *  editable where the part file holds it: numbers and PARAMS expressions, booleans, enumerations, vectors and links. */
export function PartObjectProps({ refKey }: { refKey: string }) {
  useStore((s) => s.units)
  const s = useStore((x) => x)
  const [part, name] = splitRef(refKey)
  const doc = s.features[part]
  const o = objectOf(doc, name)
  if (!doc || !o) return null
  if (o.type === SKETCH) return <Group title="Base"><Row k="Label" v={o.name} /><Row k="Geometry" v={`[${(o.geometry ?? []).length} elements]`} /><Row k="Constraints" v={`[${(o.constraints ?? []).length} constraints]`} /></Group>
  const rows: PartProp[] = PART_PROPS[o.type] ?? []
  const vars = Object.fromEntries(Object.entries(doc.params).filter(([, v]) => typeof v === 'number').map(([k, v]) => [k, { value: v as number, dims: [0, 0, 0, 0, 0, 0, 0, 0] as quantity.Quantity['dims'] }]))
  const set = (props: Record<string, unknown>) => {
    const k = Object.keys(props)[0]
    const prop = rows.find((r) => r.k === k)?.p ?? k
    void applyOps(part, [{ op: 'set', name, props }], { name: `Edit ${name}.${prop}`,
      line: `cad feature set ${s.slug} ${part} ${name} ${Object.entries(props).map(([a, b]) => `${a}=${typeof b === 'string' ? b : JSON.stringify(b)}`).join(' ')}` })
  }
  const groups = [...new Set(rows.map((r) => r.g))]
  // AttachExtension's rows are the attachment the Body built (feature_attach.body_info), as the editor wrote it: the
  // placement it gives the object, the MapMode it used and its references (a PropertyLinkSubList: "Base:Face6")
  const att = attachedOf(o)
  const attRefs = (o.attachment_support as unknown[] | undefined) ?? []
  const refsText = attRefs.map((x) => Array.isArray(x) ? (x[1] ? `${x[0]}:${x[1]}` : String(x[0])) : linkText(x)).join(', ')
  const row = (r: PartProp): ReactNode => {
    const v = r.k ? (o[r.k] as unknown) : undefined
    const label = human(r.p)
    if (r.p === 'Label') return <EditRow key={r.p} k="Label" value={labelOf(o)} type="str" onCommit={(x) => set({ label: String(x) === name ? null : x })} />
    if (r.p === 'Placement') return <Row key={r.p} k={label} v={placementText(att ? [att.placement.position, att.placement.ypr] : v ?? [[0, 0, 0], [0, 0, 0]])} />
    if (!r.k || r.ro) return <Row key={r.p} k={<span title={r.k ? 'Read-only' : 'not held by the part file: FreeCAD\'s value'}>{label}</span>}
      v={r.k ? String(v ?? '') : r.p === 'MapMode' ? String(att?.map_mode ?? o.map_mode ?? 'Deactivated') : r.p === 'AttacherEngine' ? 'Engine 3D'
        : r.p === 'AttachmentSupport' ? refsText : ''} />
    if (/PropertyLink/.test(r.t)) return <Row key={r.p} k={<span title="a link: change it in its task panel, or with cad feature set">{label}</span>} v={linkText(v)} />
    if (r.t === 'App::PropertyBool') return <EditRow key={r.p} k={label} value={v === true} type="bool" onCommit={(x) => set({ [r.k!]: x })} />
    if (r.e) return <div key={r.p} className="prow" tabIndex={0}><span className="pk" style={propPad(0)}>{label}</span>
      <span className="pv"><QComboBox className="qselect-pv" value={String(v)} onChange={(e) => set({ [r.k!]: e.target.value })}>{r.e.map((x) => <option key={x}>{x}</option>)}</QComboBox></span></div>
    if (r.t === 'App::PropertyVector' || r.t === 'App::PropertyVectorList' || r.t === 'App::PropertyFilletEdges' || r.k === 'items') return <Row key={r.p} k={label} v={linkText(v)} />
    const length = /Length|Distance/.test(r.t), angle = /Angle/.test(r.t)
    if (length || angle || /Float|Integer|Quantity/.test(r.t)) {
      const n = numberOf(v, doc.params) ?? 0
      return <EditRow key={r.p} k={label} value={n} type="float" kind={length ? 'Length' : angle ? 'Angle' : null} vars={vars} owner={o.name}
        onCommit={(x) => set({ [r.k!]: /Integer/.test(r.t) ? Math.round(Number(x)) : x })} onExpr={(text) => set({ [r.k!]: text })} note={typeof v === 'string' ? `= ${v}` : undefined} />
    }
    return <EditRow key={r.p} k={label} value={String(v ?? '')} type="str" onCommit={(x) => set({ [r.k!]: x })} />
  }
  void qtext; void LEN; void ANG
  return <>{groups.map((g) => <Group key={g} title={g}>{rows.filter((r) => r.g === g).map(row)}</Group>)}</>
}

// ── what the 3D view draws: the document's sketches shown ─────────────────────────────────────────────────────────────
let shownKey = ''
subscribe(() => {
  const s = getState(), v = getView()
  if (!v) return
  const items: [Feature, Body | undefined][] = []
  for (const [part, doc] of Object.entries(s.features)) {
    if (!isPartDoc(doc)) continue
    for (const o of doc.objects ?? []) if (o.type === SKETCH && sketchShownOf(s, part, o.name)) items.push([o, bodyOfPart(s, part)])
  }
  const key = JSON.stringify(items.map(([f, b]) => [f.name, f.geometry, f.support, f.attachment_offset, b?.matrix]))
  if (key === shownKey) return
  shownKey = key
  const g = new THREE.Group()
  for (const [f, b] of items) { const o = sketchObject(f, b); if (o) g.add(o) }
  v.setHelper('part-sketches', g.children.length ? g : null)
})
